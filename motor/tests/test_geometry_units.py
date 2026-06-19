from coordination.core.units import infer_units_from_geometry, reconcile_units


def _outline_geometry(width: float, height: float) -> list[dict[str, list[float]]]:
    return [
        {"model_bounds": [0.0, 0.0, 1.0, 1.0], "model_center": [0.0, 0.0]},
        {"model_bounds": [width, height, width + 1.0, height + 1.0], "model_center": [width, height]},
    ]


def test_infer_units_from_geometry_uses_serena_arq_mm_outline() -> None:
    inference = infer_units_from_geometry(
        {
            "outline_bounds": [0.0, 0.0, 75_699.0, 26_445.0],
        }
    )

    assert inference.unit_label == "mm"
    assert inference.factor_to_meters == 0.001
    assert inference.outline_after == (75.699, 26.445)


def test_reconcile_units_trusts_geometry_when_insunits_disagrees() -> None:
    inference = infer_units_from_geometry({"outline_bounds": [0.0, 0.0, 75_699.0, 26_445.0]})
    reconciliation = reconcile_units(1, inference, discipline="ARQ")

    assert reconciliation.factor_to_meters == 0.001
    assert reconciliation.source == "geometry_over_declared_insunits"
    assert reconciliation.warning is not None
    assert reconciliation.warning["decision"] == "trusted_geometry_over_insunits"


def test_reconcile_units_keeps_declared_when_geometry_agrees() -> None:
    inference = infer_units_from_geometry(_outline_geometry(75_699.0, 26_445.0))
    reconciliation = reconcile_units(4, inference, discipline="ARQ")

    assert reconciliation.factor_to_meters == 0.001
    assert reconciliation.source == "declared_insunits_agrees"
    assert reconciliation.warning is None
