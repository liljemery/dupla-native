from app.domain.business_pliego import (
    BUSINESS_PLIEGO_KEY,
    BUSINESS_PLIEGO_SECTION_KEYS,
    MIN_SECTION_LEN,
    default_empty_sections,
    pliego_sections_incomplete_message,
    transition_blockers_for_business_pliego,
)


def _full_sections(text: str = "x" * MIN_SECTION_LEN) -> dict[str, str]:
    s = default_empty_sections()
    for k in BUSINESS_PLIEGO_SECTION_KEYS:
        s[k] = text
    return s


def test_transition_legacy_summary_only():
    spec = {"summary": "y" * MIN_SECTION_LEN}
    assert transition_blockers_for_business_pliego(spec) is None


def test_transition_legacy_summary_short():
    spec = {"summary": "short"}
    assert transition_blockers_for_business_pliego(spec) is not None


def test_transition_structured_incomplete_section():
    sec = _full_sections()
    sec["scope"] = "ab"
    spec = {
        BUSINESS_PLIEGO_KEY: {
            "schema_version": 1,
            "sections": sec,
            "approved": True,
        }
    }
    assert transition_blockers_for_business_pliego(spec) is not None


def test_transition_structured_not_approved():
    spec = {
        BUSINESS_PLIEGO_KEY: {
            "schema_version": 1,
            "sections": _full_sections(),
            "approved": False,
        }
    }
    msg = transition_blockers_for_business_pliego(spec)
    assert msg is not None
    assert "aprobado" in msg.lower()


def test_transition_structured_ok():
    spec = {
        BUSINESS_PLIEGO_KEY: {
            "schema_version": 1,
            "sections": _full_sections(),
            "approved": True,
        }
    }
    assert transition_blockers_for_business_pliego(spec) is None


def test_pliego_sections_incomplete_message():
    bad = default_empty_sections()
    for k in BUSINESS_PLIEGO_SECTION_KEYS:
        bad[k] = "ab"
    spec = {BUSINESS_PLIEGO_KEY: {"schema_version": 1, "sections": bad}}
    assert pliego_sections_incomplete_message(spec) is not None


def _construction_lines_full() -> dict[str, dict[str, str]]:
    from app.domain.construction_pliego import EXPECTED_ITEM_IDS

    row = {"unidad": "m2", "cantidad": "10", "unitario": "5"}
    return {k: dict(row) for k in EXPECTED_ITEM_IDS}


def test_transition_construction_pliego_ok():
    spec = {
        "construction_pliego": {"schema_version": 1, "lines": _construction_lines_full()},
        BUSINESS_PLIEGO_KEY: {
            "schema_version": 1,
            "sections": _full_sections(),
            "approved": True,
        },
    }
    assert transition_blockers_for_business_pliego(spec) is None


def test_transition_construction_pliego_incomplete_line():
    lines = _construction_lines_full()
    lines["2.3"]["cantidad"] = ""
    spec = {
        "construction_pliego": {"schema_version": 1, "lines": lines},
        BUSINESS_PLIEGO_KEY: {
            "schema_version": 1,
            "sections": _full_sections(),
            "approved": True,
        },
    }
    assert transition_blockers_for_business_pliego(spec) is not None


def test_pliego_sections_incomplete_message_construction_incomplete():
    lines = _construction_lines_full()
    lines["3.1"]["unidad"] = ""
    spec = {
        "construction_pliego": {"schema_version": 1, "lines": lines},
        BUSINESS_PLIEGO_KEY: {"schema_version": 1, "sections": _full_sections()},
    }
    assert pliego_sections_incomplete_message(spec) is not None


def _ga_fo_terminal_item_states() -> dict[str, dict[str, str]]:
    from app.domain.ga_fo_01_arquitectura import expected_ga_fo_item_ids

    row = {"estado": "COMPLETO"}
    return {k: dict(row) for k in expected_ga_fo_item_ids()}


def test_transition_ga_fo_not_approved():
    spec = {
        "ga_fo_01_arquitectura": {
            "schema_version": 1,
            "item_states": _ga_fo_terminal_item_states(),
            "approved": False,
        }
    }
    msg = transition_blockers_for_business_pliego(spec)
    assert msg is not None
    assert "aprobado" in msg.lower()


def test_transition_ga_fo_ok():
    spec = {
        "ga_fo_01_arquitectura": {
            "schema_version": 1,
            "item_states": _ga_fo_terminal_item_states(),
            "approved": True,
        }
    }
    assert transition_blockers_for_business_pliego(spec) is None


def test_transition_ga_fo_ok_with_stale_business_pliego_unapproved():
    spec = {
        "ga_fo_01_arquitectura": {
            "schema_version": 1,
            "item_states": _ga_fo_terminal_item_states(),
            "approved": True,
        },
        BUSINESS_PLIEGO_KEY: {
            "schema_version": 1,
            "sections": default_empty_sections(),
            "approved": False,
        },
    }
    assert transition_blockers_for_business_pliego(spec) is None


def test_pliego_sections_incomplete_message_ga_fo_incomplete():
    spec = {
        "ga_fo_01_arquitectura": {
            "schema_version": 1,
            "item_states": {"2.1.": {"estado": "PENDIENTE"}},
        }
    }
    assert pliego_sections_incomplete_message(spec) is not None


def test_pliego_sections_incomplete_message_ga_fo_complete():
    spec = {
        "ga_fo_01_arquitectura": {
            "schema_version": 1,
            "item_states": _ga_fo_terminal_item_states(),
        }
    }
    assert pliego_sections_incomplete_message(spec) is None
