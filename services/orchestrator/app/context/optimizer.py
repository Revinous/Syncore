from __future__ import annotations

from abc import ABC, abstractmethod
from textwrap import shorten

from services.memory import MemoryStoreProtocol

from app.context.retrieval_refs import (
    build_ref_id,
    build_retrieval_hint,
    estimate_tokens,
    render_reference_placeholder,
    summarize_for_reference,
)
from app.context.schemas import (
    ContextOptimizationPolicy,
    ContextReference,
    ContextSection,
    OptimizedContextBundle,
    RawContextBundle,
)


class ContextOptimizer(ABC):
    @abstractmethod
    def optimize(
        self,
        bundle: RawContextBundle,
        policy: ContextOptimizationPolicy,
    ) -> OptimizedContextBundle:
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, ref_id: str) -> ContextReference:
        raise NotImplementedError


class SimpleContextOptimizer(ContextOptimizer):
    LOG_LIKE_TYPES = {"log_output", "tool_output", "file_content"}
    EVENT_LIKE_TYPES = {"project_event", "memory"}

    def __init__(self, store: MemoryStoreProtocol) -> None:
        self._store = store

    def optimize(
        self,
        bundle: RawContextBundle,
        policy: ContextOptimizationPolicy,
    ) -> OptimizedContextBundle:
        included_refs: list[str] = []
        warnings: list[str] = []
        optimized_sections: list[ContextSection] = []
        running_tokens = 0

        event_section_indexes = [
            index
            for index, section in enumerate(bundle.sections)
            if section.section_type in self.EVENT_LIKE_TYPES
        ]
        full_event_start = max(0, len(event_section_indexes) - policy.recent_events_full_count)
        keep_full_event_indexes = set(event_section_indexes[full_event_start:])

        for index, section in enumerate(bundle.sections):
            optimized, created_ref = self._transform_section(
                section=section,
                policy=policy,
                keep_full_event=index in keep_full_event_indexes,
                task_id=bundle.task_id,
            )
            if created_ref is not None:
                included_refs.append(created_ref)

            section_tokens = estimate_tokens(optimized.content) + 10
            if running_tokens + section_tokens <= policy.token_budget:
                optimized_sections.append(optimized)
                running_tokens += section_tokens
                continue

            if optimized.is_critical:
                optimized_sections.append(optimized)
                running_tokens += section_tokens
                warnings.append(
                    "Critical section "
                    f"'{optimized.title}' exceeded budget but was preserved verbatim."
                )
                continue

            remaining_budget = max(policy.token_budget - running_tokens, 0)
            reduced = self._reduce_noncritical_section(optimized, policy, remaining_budget)
            reduced_tokens = estimate_tokens(reduced.content) + 10
            if reduced.content and reduced_tokens <= remaining_budget:
                optimized_sections.append(reduced)
                running_tokens += reduced_tokens
                continue

            warnings.append(
                f"Skipped non-critical section '{optimized.title}' due to token budget."
            )

        rendered_prompt = self._render_prompt(optimized_sections)
        estimated = estimate_tokens(rendered_prompt)
        optimized_context = {
            "rendered_prompt": rendered_prompt,
            "section_count": len(optimized_sections),
            "metadata": bundle.metadata,
        }

        return OptimizedContextBundle(
            task_id=bundle.task_id,
            target_agent=bundle.target_agent,
            target_model=bundle.target_model,
            token_budget=policy.token_budget,
            estimated_token_count=estimated,
            optimized_context=optimized_context,
            sections=optimized_sections,
            included_refs=sorted(set(included_refs)),
            warnings=warnings,
        )

    def retrieve(self, ref_id: str) -> ContextReference:
        reference_row = self._store.get_context_reference(ref_id)
        if reference_row is None:
            raise LookupError("Context reference not found")
        return ContextReference.model_validate(reference_row)

    def _transform_section(
        self,
        *,
        section: ContextSection,
        policy: ContextOptimizationPolicy,
        keep_full_event: bool,
        task_id,
    ) -> tuple[ContextSection, str | None]:
        preserve = section.is_critical or section.section_type in policy.preserve_section_types
        content = section.content
        created_ref: str | None = None

        if (
            section.section_type in self.LOG_LIKE_TYPES
            and len(content) > policy.large_content_threshold_chars
            and not preserve
        ):
            reference = self._save_reference(task_id, section.section_type, content)
            error_snippets = self._extract_error_lines(content)
            placeholder = render_reference_placeholder(
                reference.ref_id,
                reference.summary,
                reference.retrieval_hint,
            )
            if error_snippets:
                placeholder = "\n".join(
                    ["Preserved exact error snippets:", *error_snippets[:4], "", placeholder]
                )
            content = placeholder
            created_ref = reference.ref_id
        elif section.section_type == "baton" and len(content) > policy.max_baton_chars:
            overflow = len(content) - policy.max_baton_chars
            content = (
                f"{content[: policy.max_baton_chars]}\n"
                f"[truncated non-critical baton details: {overflow} chars]"
            )
        elif section.section_type in self.EVENT_LIKE_TYPES and not keep_full_event and not preserve:
            content = self._summarize(content, policy.max_event_summary_chars)
        elif len(content) > policy.max_noncritical_chars and not preserve:
            content = self._summarize(content, policy.max_noncritical_chars)

        return section.model_copy(update={"content": content}), created_ref

    def _reduce_noncritical_section(
        self,
        section: ContextSection,
        policy: ContextOptimizationPolicy,
        remaining_budget_tokens: int,
    ) -> ContextSection:
        if remaining_budget_tokens <= 12:
            return section.model_copy(update={"content": ""})

        remaining_chars = max((remaining_budget_tokens * 4) - 40, 0)
        bounded_chars = min(remaining_chars, policy.max_event_summary_chars)
        if bounded_chars < 80:
            return section.model_copy(update={"content": ""})

        content = self._summarize(section.content, bounded_chars)
        return section.model_copy(update={"content": content})

    def _summarize(self, text: str, max_chars: int) -> str:
        compact = " ".join(text.split())
        return shorten(compact, width=max_chars, placeholder=" ...")

    def _save_reference(
        self,
        task_id,
        content_type: str,
        original_content: str,
    ) -> ContextReference:
        ref_id = build_ref_id(task_id, content_type, original_content)
        summary = summarize_for_reference(original_content)
        retrieval_hint = build_retrieval_hint(ref_id, content_type)
        row = self._store.upsert_context_reference(
            ref_id=ref_id,
            task_id=task_id,
            content_type=content_type,
            original_content=original_content,
            summary=summary,
            retrieval_hint=retrieval_hint,
        )
        return ContextReference.model_validate(row)

    def _extract_error_lines(self, text: str) -> list[str]:
        lines = [
            self._summarize(line, 160) for line in text.splitlines() if self._looks_like_error(line)
        ]
        return lines

    def _looks_like_error(self, line: str) -> bool:
        lowered = line.lower()
        return any(
            marker in lowered for marker in ("error", "exception", "traceback", "fatal", "failed")
        )

    def _render_prompt(self, sections: list[ContextSection]) -> str:
        blocks: list[str] = []
        for section in sections:
            blocks.append(f"## {section.title}\n{section.content}")
        return "\n\n".join(blocks)
