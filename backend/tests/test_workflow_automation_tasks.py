from uuid import UUID

from app.domain.workflow_automation_tasks import (
    append_automation_card_uuid,
    automation_card_uuids,
    legacy_automation_titles,
)


def test_append_and_collect_automation_card_uuids():
    card_id = UUID("11111111-1111-4111-8111-111111111111")
    auto = append_automation_card_uuid({}, card_id)
    auto = append_automation_card_uuid(auto, card_id)
    assert auto["card_uuids"] == [str(card_id)]

    meta = {"automation_tasks": auto}
    assert automation_card_uuids(meta) == frozenset({card_id})


def test_legacy_automation_titles_from_flags():
    meta = {"automation_tasks": {"enter_architecture_review": True}}
    titles = legacy_automation_titles(meta)
    assert "Revisión técnica documental (entrada a revisión de arquitectura)" in titles
