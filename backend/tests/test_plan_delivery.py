import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_plan_delivery_crud(client: AsyncClient, master_auth_headers_async: dict[str, str]):
    create = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={"name": "Obra control planos", "client_name": "Cliente", "project_kind": "CLIENT"},
    )
    assert create.status_code == 201, create.text
    pid = create.json()["uuid"]
    project_uuid = uuid.UUID(pid)

    empty = await client.get(
        f"/api/projects/{project_uuid}/plan-delivery-requests",
        headers=master_auth_headers_async,
    )
    assert empty.status_code == 200
    assert empty.json() == []

    post = await client.post(
        f"/api/projects/{project_uuid}/plan-delivery-requests",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"description": "Plano de losas", "status": "SOLICITADO"},
    )
    assert post.status_code == 201, post.text
    row = post.json()
    assert row["request_number"] == "SDP 0001"
    assert row["sequence_number"] == 1
    assert row["description"] == "Plano de losas"
    row_uuid = row["uuid"]

    listed = await client.get(
        f"/api/projects/{project_uuid}/plan-delivery-requests",
        headers=master_auth_headers_async,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patch = await client.patch(
        f"/api/projects/{project_uuid}/plan-delivery-requests/{row_uuid}",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"status": "ENTREGADO", "description": "Plano de losas v2"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["status"] == "ENTREGADO"
    assert patch.json()["description"] == "Plano de losas v2"

    xlsx = await client.get(
        f"/api/projects/{project_uuid}/exports/control-planos.xlsx",
        headers=master_auth_headers_async,
    )
    assert xlsx.status_code == 200
    assert xlsx.headers.get("content-type", "").startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    pdf = await client.get(
        f"/api/projects/{project_uuid}/exports/control-planos.pdf",
        headers=master_auth_headers_async,
    )
    assert pdf.status_code == 200
    assert pdf.headers.get("content-type", "").startswith("application/pdf")

    delete = await client.delete(
        f"/api/projects/{project_uuid}/plan-delivery-requests/{row_uuid}",
        headers=master_auth_headers_async,
    )
    assert delete.status_code == 204

    after = await client.get(
        f"/api/projects/{project_uuid}/plan-delivery-requests",
        headers=master_auth_headers_async,
    )
    assert after.json() == []
