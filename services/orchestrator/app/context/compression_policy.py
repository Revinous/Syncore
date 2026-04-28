from app.context.schemas import ContextOptimizationPolicy


def default_context_policy(
    token_budget: int, *, layering_enabled: bool = False
) -> ContextOptimizationPolicy:
    return ContextOptimizationPolicy(
        token_budget=token_budget,
        layering_enabled=layering_enabled,
        preserve_section_types={"constraint", "error", "schema", "code_patch"},
        large_content_threshold_chars=2_000,
        max_baton_chars=3_500,
        recent_events_full_count=4,
        max_event_summary_chars=400,
        max_noncritical_chars=700,
    )
