from app.domain.models import Catalog, LessonPlan, RevisionPlan


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


def validate_revision_plan(
    plan: RevisionPlan, catalog: Catalog
) -> tuple[bool, str | None]:
    known_claims = set(catalog.claims)
    known_content = {item.content_id for item in catalog.items}
    allowed = set(plan.allowed_claim_ids)

    if [slot.order for slot in plan.schedule] != list(range(1, len(plan.schedule) + 1)):
        return False, "SLOT_ORDER_INVALID"
    keys = [(slot.offset_days, slot.concept_id) for slot in plan.schedule]
    if keys != sorted(keys):
        return False, "SLOT_ORDER_INVALID"
    if any(slot.offset_days > plan.horizon_days for slot in plan.schedule):
        return False, "SLOT_BEYOND_HORIZON"

    if not allowed <= known_claims:
        return False, "UNKNOWN_CLAIM_ID"

    items = plan.exercise_set.items
    if [item.order for item in items] != list(range(1, len(items) + 1)):
        return False, "ITEM_ORDER_INVALID"

    for item in items:
        if not set(item.claim_ids) <= allowed:
            return False, "ITEM_CLAIM_NOT_ALLOWED"
        generated_id = item.content_ref.content_id.startswith("generated_")
        if item.derived_from is None:
            # A catalog item must actually be in the catalog.
            if generated_id or item.content_ref.content_id not in known_content:
                return False, "UNKNOWN_CONTENT_ID"
        elif not generated_id:
            # Anything claiming generator provenance must carry a generated id.
            return False, "GENERATED_ITEM_INVALID"
    return True, None
