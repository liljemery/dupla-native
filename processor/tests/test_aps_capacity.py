"""APS quota / capacity detection."""

from aps_integration.model_derivative import is_capacity_denied


def test_is_capacity_denied_product_access() -> None:
    body = '{"reason":"ProductAccessRequiresCapacity"}'
    assert is_capacity_denied(403, body)


def test_is_capacity_denied_generic_forbidden() -> None:
    assert is_capacity_denied(403, "Forbidden")
