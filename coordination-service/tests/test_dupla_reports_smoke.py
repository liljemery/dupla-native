"""Smoke fixture adaptation must preserve real file discipline labels."""

from adapters.dupla_reports import adapt_smoke_primary


def test_adapt_smoke_primary_maps_electric_pair_disciplines() -> None:
    primary = {
        "incidents": [
            {
                "incident_id": "incident_0001",
                "file_pair": ["ARQ-PLANTA.dwg", "EST-LOSAS.dwg"],
                "representative_conflict": {
                    "discipline_a": "ARQUITECTURA",
                    "discipline_b": "ESTRUCTURA",
                    "clash_type": "HARD",
                },
            }
        ]
    }
    file_entries = [
        {
            "original_name": "PLANOS ARQ.dwg",
            "discipline_bucket": "arquitectura",
        },
        {
            "original_name": "PLANOS ELECTRICOS.dwg",
            "discipline_bucket": "electrica",
        },
    ]

    adapted = adapt_smoke_primary(primary, file_entries)
    incident = adapted["incidents"][0]
    rep = incident["representative_conflict"]

    assert incident["file_pair"] == ["PLANOS ARQ.dwg", "PLANOS ELECTRICOS.dwg"]
    assert rep["discipline_a"] == "ARQUITECTURA"
    assert rep["discipline_b"] == "ELECTRICIDAD"


def test_adapt_smoke_primary_keeps_estructura_when_bucket_present() -> None:
    primary = {
        "incidents": [
            {
                "representative_conflict": {
                    "discipline_a": "ARQUITECTURA",
                    "discipline_b": "ESTRUCTURA",
                },
            }
        ]
    }
    file_entries = [
        {"original_name": "A.dwg", "discipline_bucket": "arquitectura"},
        {"original_name": "E.dwg", "discipline_bucket": "estructura"},
    ]

    adapted = adapt_smoke_primary(primary, file_entries)
    rep = adapted["incidents"][0]["representative_conflict"]
    assert rep["discipline_a"] == "ARQUITECTURA"
    assert rep["discipline_b"] == "ESTRUCTURA"
