import io
import uuid

import pytest

from app.domain.project_default_areas import ESTIMATED_CONSTRUCTION_AREA_NAME


@pytest.mark.asyncio
async def test_login_ok(client):
    res = await client.post(
        "/api/auth/token",
        data={"username": "tester@dupla.demo", "password": "testpass123"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body


@pytest.mark.asyncio
async def test_login_fail(client):
    res = await client.post(
        "/api/auth/token",
        data={"username": "tester@dupla.demo", "password": "wrong"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    res = await client.get("/api/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_ok(client, auth_headers_async: dict[str, str]):
    res = await client.get("/api/me", headers=auth_headers_async)
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "tester@dupla.demo"


@pytest.mark.asyncio
async def test_modules_cached_flow(client, auth_headers_async: dict[str, str]):
    a = await client.get("/api/modules", headers=auth_headers_async)
    b = await client.get("/api/modules", headers=auth_headers_async)
    assert a.status_code == 200
    assert b.status_code == 200
    assert a.json() == b.json()


@pytest.mark.asyncio
async def test_coordinator_cannot_create_project(client, auth_headers_async: dict[str, str]):
    res = await client.post(
        "/api/projects",
        headers=auth_headers_async,
        data={"name": "No debe existir"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_project_architecture_flow(client, master_auth_headers_async: dict[str, str]):
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Obra demo", "client_name": "Cliente", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201, create.text
    created = create.json()
    assert created["project_kind"] == "CLIENT"
    assert created["workflow_phase"] == "AWAITING_FILES"
    pid = created["uuid"]
    project_uuid = uuid.UUID(pid)

    get_arch = await client.get(
        f"/api/projects/{project_uuid}/architecture",
        headers=master_auth_headers_async,
    )
    assert get_arch.status_code == 200
    groups = get_arch.json()["document"]["groups"]
    assert len(groups) == 1
    assert groups[0]["title"] == ESTIMATED_CONSTRUCTION_AREA_NAME
    assert groups[0]["kind"] == "fase"

    folders = await client.get(
        f"/api/projects/{project_uuid}/file-folders",
        headers=master_auth_headers_async,
    )
    assert folders.status_code == 200
    folder_names = [f["name"] for f in folders.json()]
    assert folder_names == [ESTIMATED_CONSTRUCTION_AREA_NAME]

    payload = {
        "groups": [
            {
                "id": str(uuid.uuid4()),
                "kind": "fase",
                "title": "Fase 1",
                "order": 0,
                "items": [
                    {
                        "id": str(uuid.uuid4()),
                        "descripcion": "Partida demo",
                        "unidad": "m2",
                        "cantidad": 10,
                        "precio_unitario": 5,
                        "subtotal": 50,
                    }
                ],
            }
        ],
        "materiales": [],
    }

    put = await client.put(
        f"/api/projects/{project_uuid}/architecture",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json=payload,
    )
    assert put.status_code == 204, put.text

    get_full = await client.get(
        f"/api/projects/{project_uuid}/architecture",
        headers=master_auth_headers_async,
    )
    assert get_full.status_code == 200
    assert len(get_full.json()["document"]["groups"]) == 1


@pytest.mark.asyncio
async def test_development_project_seeds_construction_and_sales_areas(
    client, master_auth_headers_async: dict[str, str],
):
    from app.domain.project_default_areas import ESTIMATED_SALES_AREA_NAME

    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Desarrollo demo", "project_kind": "DEVELOPMENT"},
    )
    assert create.status_code == 201, create.text
    project_uuid = create.json()["uuid"]

    folders = await client.get(
        f"/api/projects/{project_uuid}/file-folders",
        headers=master_auth_headers_async,
    )
    assert folders.status_code == 200
    names = [f["name"] for f in folders.json()]
    assert names == [ESTIMATED_CONSTRUCTION_AREA_NAME, ESTIMATED_SALES_AREA_NAME]

    arch = await client.get(
        f"/api/projects/{project_uuid}/architecture",
        headers=master_auth_headers_async,
    )
    assert arch.status_code == 200
    titles = [g["title"] for g in arch.json()["document"]["groups"]]
    assert titles == [ESTIMATED_CONSTRUCTION_AREA_NAME, ESTIMATED_SALES_AREA_NAME]


@pytest.mark.asyncio
async def test_tender_project_starts_in_architecture_review_with_file(
    client, master_auth_headers_async: dict[str, str]
):
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Licitación demo", "client_name": "Cliente", "project_kind": "TENDER"},
        files=[("files", ("pliego.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf"))],
    )
    assert create.status_code == 201, create.text
    created = create.json()
    assert created["project_kind"] == "TENDER"
    assert created["workflow_phase"] == "AWAITING_FILES"
    pid = created["uuid"]

    t2 = await client.post(
        f"/api/projects/{pid}/transitions",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"target_phase": "ARCHITECTURE_REVIEW"},
    )
    assert t2.status_code == 200, t2.text

    get_p = await client.get(f"/api/projects/{pid}", headers=master_auth_headers_async)
    assert get_p.status_code == 200
    assert get_p.json()["workflow_phase"] == "ARCHITECTURE_REVIEW"

    rewind = await client.post(
        f"/api/projects/{pid}/transitions",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"target_phase": "AWAITING_FILES"},
    )
    assert rewind.status_code == 409, rewind.text
    assert "licitación" in rewind.json()["detail"].lower()


@pytest.mark.asyncio
async def test_exports_return_bytes(client, master_auth_headers_async: dict[str, str]):
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Export demo", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201
    assert create.json()["project_kind"] == "CLIENT"
    assert create.json()["workflow_phase"] == "AWAITING_FILES"
    pid = uuid.UUID(create.json()["uuid"])

    xlsx = await client.get(f"/api/projects/{pid}/exports/pliego.xlsx", headers=master_auth_headers_async)
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"

    pdf = await client.get(f"/api/projects/{pid}/exports/pliego.pdf", headers=master_auth_headers_async)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    doc_pdf = await client.get(
        f"/api/projects/{pid}/exports/documentary-report.pdf",
        headers=master_auth_headers_async,
    )
    assert doc_pdf.status_code == 200
    assert doc_pdf.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_pliego_generate_approve_and_transition_to_budget(
    client, master_auth_headers_async: dict[str, str]
):
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Pliego flow", "client_name": "C", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201, create.text
    pid = create.json()["uuid"]

    up = await client.post(
        f"/api/projects/{pid}/files",
        headers=master_auth_headers_async,
        files=[("file", ("p.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf"))],
    )
    assert up.status_code == 201, up.text

    t2 = await client.post(
        f"/api/projects/{pid}/transitions",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"target_phase": "ARCHITECTURE_REVIEW"},
    )
    assert t2.status_code == 200, t2.text

    rev = await client.post(
        f"/api/projects/{pid}/architecture-revisions",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"decision": "APPROVED", "notes": "ok", "checklist": {}},
    )
    assert rev.status_code == 201, rev.text

    t3 = await client.post(
        f"/api/projects/{pid}/transitions",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"target_phase": "SPECIFICATIONS"},
    )
    assert t3.status_code == 200, t3.text

    gen = await client.post(
        f"/api/projects/{pid}/specifications/generate",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"force": False},
    )
    assert gen.status_code == 200, gen.text
    spec = gen.json().get("specifications_document") or {}
    assert "business_pliego" in spec

    block_fail = await client.post(
        f"/api/projects/{pid}/transitions",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"target_phase": "BUDGETING_PIPELINE"},
    )
    assert block_fail.status_code == 409, block_fail.text

    ap = await client.post(
        f"/api/projects/{pid}/specifications/approve",
        headers=master_auth_headers_async,
    )
    assert ap.status_code == 200, ap.text
    assert ap.json()["specifications_document"]["business_pliego"]["approved"] is True

    tb = await client.post(
        f"/api/projects/{pid}/transitions",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"target_phase": "BUDGETING_PIPELINE"},
    )
    assert tb.status_code == 200, tb.text
    assert tb.json()["workflow_phase"] == "BUDGETING_PIPELINE"


@pytest.mark.asyncio
async def test_upload_allowed_in_awaiting_files(client, master_auth_headers_async: dict[str, str]):
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Upload bootstrap", "client_name": "C", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201, create.text
    pid = create.json()["uuid"]

    up = await client.post(
        f"/api/projects/{pid}/files",
        headers=master_auth_headers_async,
        files=[("file", ("arranque.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf"))],
    )
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["counts_for_budget"] is True


def test_upload_counts_for_budget_by_phase():
    from app.domain.workflow_phase import WorkflowPhase, upload_counts_for_budget

    assert upload_counts_for_budget(WorkflowPhase.AWAITING_FILES) is True
    assert upload_counts_for_budget(WorkflowPhase.BUDGETING_PIPELINE) is True
    assert upload_counts_for_budget(WorkflowPhase.MANAGEMENT_APPROVAL) is False
    assert upload_counts_for_budget(WorkflowPhase.COMPLETE) is False

