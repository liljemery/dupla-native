from app.schemas.clash_viewer import ClashMappingCandidatesResponse


def test_mapping_candidates_empty_response_is_valid() -> None:
    response = ClashMappingCandidatesResponse(
        clash_id="CL-0001",
        candidates=[],
        strategy="not_implemented",
        warnings=[{"code": "DBID_MAPPING_NOT_IMPLEMENTED", "message": "Pendiente"}],
    )

    assert response.viewer_dbid_a is None
    assert response.viewer_dbid_b is None
    assert response.candidates == []
    assert response.warnings[0].code == "DBID_MAPPING_NOT_IMPLEMENTED"
