import hashlib
from textwrap import shorten
from uuid import UUID


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def build_ref_id(task_id: UUID, content_type: str, original_content: str) -> str:
    content_hash = hashlib.sha1(original_content.encode("utf-8")).hexdigest()[:14]
    type_tag = content_type.replace(" ", "_").lower()[:18]
    return f"ctxref_{task_id.hex[:8]}_{type_tag}_{content_hash}"


def summarize_for_reference(content: str, max_chars: int = 240) -> str:
    compact = " ".join(content.split())
    return shorten(compact, width=max_chars, placeholder=" ...")


def build_retrieval_hint(ref_id: str, content_type: str) -> str:
    return (
        f"Retrieve full {content_type} via GET /context/references/{ref_id} "
        f"when exact raw bytes are needed."
    )


def render_reference_placeholder(ref_id: str, summary: str, retrieval_hint: str) -> str:
    return "\n".join(
        [
            f"[context_ref:{ref_id}]",
            f"summary: {summary}",
            retrieval_hint,
        ]
    )
