"""Discipline alias tests for project file buckets."""

from app.domain.file_discipline import discipline_bucket, parse_discipline, FileDiscipline


def test_fontaneria_maps_to_plomeria_bucket() -> None:
    assert discipline_bucket("fontaneria") == "plomeria"
    assert parse_discipline("fontaneria") == FileDiscipline.PLOMERIA


def test_sanitario_maps_to_plomeria_bucket() -> None:
    assert discipline_bucket("sanitario") == "plomeria"
    assert parse_discipline("sanitaria") == FileDiscipline.PLOMERIA


def test_electrico_maps_to_electrica_bucket() -> None:
    assert discipline_bucket("electrico") == "electrica"
    assert parse_discipline("electricidad") == FileDiscipline.ELECTRICA
