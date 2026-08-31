from app.domain.models import Catalog, LessonPlan


def validate_plan(plan: LessonPlan, catalog: Catalog) -> tuple[bool, str | None]:
    known_claims = set(catalog.claims)
    expected_orders = list(range(1, len(plan.blocks) + 1))
    if [block.order for block in plan.blocks] != expected_orders:
        return False, "BLOCK_ORDER_INVALID"
    if not set(plan.allowed_claim_ids) <= known_claims:
        return False, "UNKNOWN_CLAIM_ID"
    for block in plan.blocks:
        if not set(block.claim_ids) <= set(plan.allowed_claim_ids):
            return False, "BLOCK_CLAIM_NOT_ALLOWED"
    return True, None

