import pytest


@pytest.mark.asyncio
async def test_admin_list_users_master_ok(client, master_auth_headers_async: dict[str, str]):
    res = await client.get("/api/admin/users", headers=master_auth_headers_async)
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    emails = {u["email"] for u in body}
    assert "master@dupla.demo" in emails
    assert "tester@dupla.demo" in emails
    assert "worker@dupla.demo" in emails


@pytest.mark.asyncio
async def test_admin_forbidden_for_coordinator(client, auth_headers_async: dict[str, str]):
    res = await client.get("/api/admin/users", headers=auth_headers_async)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_forbidden_for_worker(client):
    res = await client.post(
        "/api/auth/token",
        data={"username": "worker@dupla.demo", "password": "workerpass123"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.get("/api/admin/users", headers=headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_create_user(client, master_auth_headers_async: dict[str, str]):
    res = await client.post(
        "/api/admin/users",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "first_name": "Nuevo",
            "last_name": "Usuario",
            "email": "newuser@dupla.demo",
            "password": "longpassword1",
            "role": "PRESUPUESTO",
            "module_ids": [1],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["email"] == "newuser@dupla.demo"
    assert res.json()["must_change_password"] is True


@pytest.mark.asyncio
async def test_new_user_must_change_password_on_login(client, master_auth_headers_async: dict[str, str]):
    create = await client.post(
        "/api/admin/users",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "first_name": "Primer",
            "last_name": "Login",
            "email": "firstlogin@dupla.demo",
            "password": "temppass123",
            "role": "PRESUPUESTO",
            "module_ids": [1],
        },
    )
    assert create.status_code == 201, create.text

    login = await client.post(
        "/api/auth/token",
        data={"username": "firstlogin@dupla.demo", "password": "temppass123"},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["must_change_password"] is True

    token = body["access_token"]
    blocked = await client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 403

    change = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"current_password": "temppass123", "new_password": "newsecure123"},
    )
    assert change.status_code == 200, change.text

    allowed = await client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_admin_delete_user(client, master_auth_headers_async: dict[str, str]):
    create = await client.post(
        "/api/admin/users",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "first_name": "Borrar",
            "last_name": "Prueba",
            "email": "delete-me@dupla.demo",
            "password": "longpassword1",
            "role": "PRESUPUESTO",
            "module_ids": [1],
        },
    )
    assert create.status_code == 201, create.text
    user_uuid = create.json()["uuid"]

    delete = await client.delete(
        f"/api/admin/users/{user_uuid}",
        headers=master_auth_headers_async,
    )
    assert delete.status_code == 204, delete.text

    listing = await client.get("/api/admin/users", headers=master_auth_headers_async)
    emails = {u["email"] for u in listing.json()}
    assert "delete-me@dupla.demo" not in emails


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(client, master_auth_headers_async: dict[str, str]):
    listing = await client.get("/api/admin/users", headers=master_auth_headers_async)
    master = next(u for u in listing.json() if u["email"] == "master@dupla.demo")

    res = await client.delete(
        f"/api/admin/users/{master['uuid']}",
        headers=master_auth_headers_async,
    )
    assert res.status_code == 400
    assert "propia" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_import_users(client, master_auth_headers_async: dict[str, str]):
    res = await client.post(
        "/api/admin/users/import",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "users": [
                {
                    "first_name": "Import",
                    "last_name": "Uno",
                    "email": "import1@dupla.demo",
                    "role": "PRESUPUESTO",
                    "module_ids": [1],
                },
                {
                    "first_name": "Import",
                    "last_name": "Dos",
                    "email": "import2@dupla.demo",
                    "role": "CONTROL",
                    "module_ids": [1],
                },
            ]
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["created"]) == 2
    assert all(len(row["password"]) >= 8 for row in body["created"])
    assert body["skipped"] == []
    assert body["errors"] == []

    again = await client.post(
        "/api/admin/users/import",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "users": [
                {
                    "first_name": "Import",
                    "last_name": "Uno",
                    "email": "import1@dupla.demo",
                    "role": "PRESUPUESTO",
                    "module_ids": [1],
                },
            ]
        },
    )
    assert again.status_code == 200, again.text
    skipped = again.json()["skipped"]
    assert len(skipped) == 1
    assert skipped[0]["email"] == "import1@dupla.demo"


async def _team_leader_headers(client, master_auth_headers_async: dict[str, str]) -> dict[str, str]:
    create = await client.post(
        "/api/admin/users",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "first_name": "Team",
            "last_name": "Leader",
            "email": "tl@dupla.demo",
            "password": "temppass123",
            "role": "CONTROL",
            "module_ids": [1],
        },
    )
    assert create.status_code == 201, create.text
    user_uuid = create.json()["uuid"]

    promote = await client.patch(
        f"/api/admin/users/{user_uuid}",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "first_name": "Team",
            "last_name": "Leader",
            "email": "tl@dupla.demo",
            "role": "CONTROL",
            "module_ids": [1],
            "is_team_leader": True,
        },
    )
    assert promote.status_code == 200, promote.text
    assert promote.json()["is_team_leader"] is True

    login = await client.post(
        "/api/auth/token",
        data={"username": "tl@dupla.demo", "password": "temppass123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    change = await client.post(
        "/api/auth/change-password",
        headers={**headers, "Content-Type": "application/json"},
        json={"current_password": "temppass123", "new_password": "newsecure123"},
    )
    assert change.status_code == 200, change.text
    return headers


@pytest.mark.asyncio
async def test_team_leader_elevated_admin_access(client, master_auth_headers_async: dict[str, str]):
    tl_headers = await _team_leader_headers(client, master_auth_headers_async)

    listing = await client.get("/api/admin/users", headers=tl_headers)
    assert listing.status_code == 200, listing.text

    me = await client.get("/api/me", headers=tl_headers)
    assert me.status_code == 200, me.text
    assert me.json()["is_team_leader"] is True


@pytest.mark.asyncio
async def test_team_leader_cannot_create_or_import_users(
    client, master_auth_headers_async: dict[str, str]
):
    tl_headers = await _team_leader_headers(client, master_auth_headers_async)

    create = await client.post(
        "/api/admin/users",
        headers={**tl_headers, "Content-Type": "application/json"},
        json={
            "first_name": "Blocked",
            "last_name": "Create",
            "email": "blocked-create@dupla.demo",
            "password": "longpassword1",
            "role": "PRESUPUESTO",
            "module_ids": [1],
        },
    )
    assert create.status_code == 403

    import_res = await client.post(
        "/api/admin/users/import",
        headers={**tl_headers, "Content-Type": "application/json"},
        json={
            "users": [
                {
                    "first_name": "Blocked",
                    "last_name": "Import",
                    "email": "blocked-import@dupla.demo",
                    "role": "PRESUPUESTO",
                    "module_ids": [1],
                },
            ]
        },
    )
    assert import_res.status_code == 403


@pytest.mark.asyncio
async def test_team_leader_cannot_assign_team_leader_or_gerencia_role(
    client, master_auth_headers_async: dict[str, str]
):
    tl_headers = await _team_leader_headers(client, master_auth_headers_async)

    victim = await client.post(
        "/api/admin/users",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "first_name": "Victim",
            "last_name": "User",
            "email": "victim@dupla.demo",
            "password": "longpassword1",
            "role": "PRESUPUESTO",
            "module_ids": [1],
        },
    )
    assert victim.status_code == 201, victim.text
    victim_uuid = victim.json()["uuid"]

    assign_tl = await client.patch(
        f"/api/admin/users/{victim_uuid}",
        headers={**tl_headers, "Content-Type": "application/json"},
        json={
            "first_name": "Victim",
            "last_name": "User",
            "email": "victim@dupla.demo",
            "role": "PRESUPUESTO",
            "module_ids": [1],
            "is_team_leader": True,
        },
    )
    assert assign_tl.status_code == 403

    promote = await client.patch(
        f"/api/admin/users/{victim_uuid}",
        headers={**tl_headers, "Content-Type": "application/json"},
        json={
            "first_name": "Victim",
            "last_name": "User",
            "email": "victim@dupla.demo",
            "role": "GERENCIA",
            "module_ids": [1],
        },
    )
    assert promote.status_code == 403


@pytest.mark.asyncio
async def test_team_leader_dashboard_and_projects(client, master_auth_headers_async: dict[str, str]):
    template = await client.post(
        "/api/workflow-templates",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"name": "Flujo TL test", "description": ""},
    )
    assert template.status_code == 201, template.text
    template_uuid = template.json()["uuid"]
    steps = await client.put(
        f"/api/workflow-templates/{template_uuid}/steps",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "steps": [
                {
                    "stable_key": "inicio",
                    "title": "Inicio",
                    "behavior_kind": "CUSTOM_AUTOMATION",
                },
            ],
        },
    )
    assert steps.status_code == 200, steps.text

    tl_headers = await _team_leader_headers(client, master_auth_headers_async)

    dashboard = await client.get("/api/dashboard/summary", headers=tl_headers)
    assert dashboard.status_code == 200, dashboard.text

    projects = await client.get("/api/projects", headers=tl_headers)
    assert projects.status_code == 200, projects.text

    create_project = await client.post(
        "/api/projects",
        headers=tl_headers,
        data={"name": "TL Project", "client_name": "Test Client", "project_kind": "CLIENT"},
    )
    assert create_project.status_code == 201, create_project.text


@pytest.mark.asyncio
async def test_delete_workflow_template_without_projects(client, master_auth_headers_async: dict[str, str]):
    template = await client.post(
        "/api/workflow-templates",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"name": "Flujo a borrar", "description": "temp"},
    )
    assert template.status_code == 201, template.text
    template_uuid = template.json()["uuid"]

    steps = await client.put(
        f"/api/workflow-templates/{template_uuid}/steps",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "steps": [
                {
                    "stable_key": "paso1",
                    "title": "Paso 1",
                    "behavior_kind": "CUSTOM_AUTOMATION",
                },
            ],
        },
    )
    assert steps.status_code == 200, steps.text

    delete = await client.delete(
        f"/api/workflow-templates/{template_uuid}",
        headers=master_auth_headers_async,
    )
    assert delete.status_code == 204, delete.text

    missing = await client.get(
        f"/api/workflow-templates/{template_uuid}",
        headers=master_auth_headers_async,
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_delete_workflow_template_with_projects_blocked(client, master_auth_headers_async: dict[str, str]):
    template = await client.post(
        "/api/workflow-templates",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"name": "Flujo con obra", "description": ""},
    )
    assert template.status_code == 201, template.text
    template_uuid = template.json()["uuid"]

    steps = await client.put(
        f"/api/workflow-templates/{template_uuid}/steps",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={
            "steps": [
                {
                    "stable_key": "inicio",
                    "title": "Inicio",
                    "behavior_kind": "CUSTOM_AUTOMATION",
                },
            ],
        },
    )
    assert steps.status_code == 200, steps.text

    project = await client.post(
        "/api/projects",
        headers=master_auth_headers_async,
        data={
            "name": "Obra en flujo",
            "client_name": "Cliente",
            "project_kind": "CLIENT",
            "workflow_template_uuid": str(template_uuid),
        },
    )
    assert project.status_code == 201, project.text

    delete = await client.delete(
        f"/api/workflow-templates/{template_uuid}",
        headers=master_auth_headers_async,
    )
    assert delete.status_code == 409, delete.text


@pytest.mark.asyncio
async def test_chat_flow(client, auth_headers_async: dict[str, str]):
    convs = await client.get("/api/chat/conversations", headers=auth_headers_async)
    assert convs.status_code == 200
    conv_list = convs.json()
    assert len(conv_list) >= 1
    general = next(c for c in conv_list if c["kind"] == "GENERAL")
    general_uuid = general["uuid"]

    empty = await client.get("/api/chat/messages", headers=auth_headers_async)
    assert empty.status_code == 200
    assert empty.json() == []

    post = await client.post(
        "/api/chat/messages",
        headers={**auth_headers_async, "Content-Type": "application/json"},
        json={"body": "Hola equipo"},
    )
    assert post.status_code == 201, post.text
    msg = post.json()
    assert msg["body"] == "Hola equipo"
    assert msg["conversation_uuid"] == general_uuid
    mid = msg["uuid"]

    again = await client.get("/api/chat/messages", headers=auth_headers_async)
    assert again.status_code == 200
    assert len(again.json()) == 1

    after = await client.get(f"/api/chat/messages?after_uuid={mid}", headers=auth_headers_async)
    assert after.status_code == 200
    assert after.json() == []

    scoped = await client.get(
        f"/api/chat/conversations/{general_uuid}/messages",
        headers=auth_headers_async,
    )
    assert scoped.status_code == 200
    assert len(scoped.json()) == 1


@pytest.mark.asyncio
async def test_chat_direct_between_users(client, auth_headers_async: dict[str, str]):
    res = await client.post(
        "/api/auth/token",
        data={"username": "worker@dupla.demo", "password": "workerpass123"},
    )
    assert res.status_code == 200
    worker_token = res.json()["access_token"]
    worker_headers = {"Authorization": f"Bearer {worker_token}"}

    me = await client.get("/api/me", headers=auth_headers_async)
    assert me.status_code == 200
    tester_uuid = me.json()["uuid"]

    open_dm = await client.post(
        "/api/chat/conversations/direct",
        headers={**worker_headers, "Content-Type": "application/json"},
        json={"user_uuid": str(tester_uuid)},
    )
    assert open_dm.status_code == 200, open_dm.text
    dm = open_dm.json()
    assert dm["kind"] == "DIRECT"
    dm_uuid = dm["uuid"]

    send = await client.post(
        f"/api/chat/conversations/{dm_uuid}/messages",
        headers={**worker_headers, "Content-Type": "application/json"},
        json={"body": "Hola coordinador"},
    )
    assert send.status_code == 201, send.text
    assert send.json()["conversation_uuid"] == dm_uuid

    tester_convs = await client.get("/api/chat/conversations", headers=auth_headers_async)
    assert tester_convs.status_code == 200
    titles = {c["uuid"]: c["display_title"] for c in tester_convs.json()}
    assert dm_uuid in titles

    msgs = await client.get(
        f"/api/chat/conversations/{dm_uuid}/messages",
        headers=auth_headers_async,
    )
    assert msgs.status_code == 200
    assert len(msgs.json()) == 1
    assert msgs.json()[0]["body"] == "Hola coordinador"


@pytest.mark.asyncio
async def test_chat_create_group(client, auth_headers_async: dict[str, str]):
    worker_login = await client.post(
        "/api/auth/token",
        data={"username": "worker@dupla.demo", "password": "workerpass123"},
    )
    assert worker_login.status_code == 200
    worker_token = worker_login.json()["access_token"]
    worker_headers = {"Authorization": f"Bearer {worker_token}"}
    worker_me = await client.get("/api/me", headers=worker_headers)
    assert worker_me.status_code == 200
    worker_uuid = worker_me.json()["uuid"]

    grp = await client.post(
        "/api/chat/conversations/group",
        headers={**auth_headers_async, "Content-Type": "application/json"},
        json={"title": "Equipo obra", "member_uuids": [str(worker_uuid)]},
    )
    assert grp.status_code == 201, grp.text
    body = grp.json()
    assert body["kind"] == "GROUP"
    assert body["display_title"] == "Equipo obra"
    gid = body["uuid"]

    post = await client.post(
        f"/api/chat/conversations/{gid}/messages",
        headers={**auth_headers_async, "Content-Type": "application/json"},
        json={"body": "Aviso del grupo"},
    )
    assert post.status_code == 201

    worker_msgs = await client.get(
        f"/api/chat/conversations/{gid}/messages",
        headers=worker_headers,
    )
    assert worker_msgs.status_code == 200
    assert len(worker_msgs.json()) == 1


@pytest.mark.asyncio
async def test_chat_delete_direct_and_group(client, auth_headers_async: dict[str, str]):
    worker_login = await client.post(
        "/api/auth/token",
        data={"username": "worker@dupla.demo", "password": "workerpass123"},
    )
    assert worker_login.status_code == 200
    worker_headers = {"Authorization": f"Bearer {worker_login.json()['access_token']}"}
    worker_me = await client.get("/api/me", headers=worker_headers)
    assert worker_me.status_code == 200
    worker_uuid = worker_me.json()["uuid"]

    dm = await client.post(
        "/api/chat/conversations/direct",
        headers={**auth_headers_async, "Content-Type": "application/json"},
        json={"user_uuid": str(worker_uuid)},
    )
    assert dm.status_code == 200, dm.text
    dm_uuid = dm.json()["uuid"]

    grp = await client.post(
        "/api/chat/conversations/group",
        headers={**auth_headers_async, "Content-Type": "application/json"},
        json={"title": "Grupo temporal", "member_uuids": [str(worker_uuid)]},
    )
    assert grp.status_code == 201, grp.text
    gid = grp.json()["uuid"]

    convs = await client.get("/api/chat/conversations", headers=auth_headers_async)
    assert convs.status_code == 200
    conv_uuids = {c["uuid"] for c in convs.json()}
    assert dm_uuid in conv_uuids
    assert gid in conv_uuids

    del_dm = await client.delete(f"/api/chat/conversations/{dm_uuid}", headers=auth_headers_async)
    assert del_dm.status_code == 204, del_dm.text

    del_grp = await client.delete(f"/api/chat/conversations/{gid}", headers=worker_headers)
    assert del_grp.status_code == 204, del_grp.text

    after = await client.get("/api/chat/conversations", headers=auth_headers_async)
    assert after.status_code == 200
    after_uuids = {c["uuid"] for c in after.json()}
    assert dm_uuid not in after_uuids
    assert gid not in after_uuids

    worker_after = await client.get("/api/chat/conversations", headers=worker_headers)
    assert worker_after.status_code == 200
    worker_uuids = {c["uuid"] for c in worker_after.json()}
    assert dm_uuid not in worker_uuids
    assert gid not in worker_uuids

    convs2 = await client.get("/api/chat/conversations", headers=auth_headers_async)
    general_uuid = next(c["uuid"] for c in convs2.json() if c["kind"] == "GENERAL")
    del_general = await client.delete(f"/api/chat/conversations/{general_uuid}", headers=auth_headers_async)
    assert del_general.status_code == 400


@pytest.mark.asyncio
async def test_task_board_gerencia_can_create_and_patch(client, master_auth_headers_async: dict[str, str]):
    board = await client.get("/api/tasks/board", headers=master_auth_headers_async)
    assert board.status_code == 200
    lists = board.json()["lists"]
    assert len(lists) >= 1

    list_uuid = lists[0]["uuid"]
    create = await client.post(
        "/api/tasks/cards",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"list_uuid": str(list_uuid), "title": "Tarea demo"},
    )
    assert create.status_code == 201, create.text
    card_id = create.json()["uuid"]

    patch = await client.patch(
        f"/api/tasks/cards/{card_id}",
        headers={**master_auth_headers_async, "Content-Type": "application/json"},
        json={"title": "Actualizado por gerencia"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["title"] == "Actualizado por gerencia"


@pytest.mark.asyncio
async def test_task_board_worker_create_and_move(client):
    res = await client.post(
        "/api/auth/token",
        data={"username": "worker@dupla.demo", "password": "workerpass123"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    board = await client.get("/api/tasks/board", headers=headers)
    assert board.status_code == 200
    lists = board.json()["lists"]
    a, b = lists[0]["uuid"], lists[1]["uuid"]

    create = await client.post(
        "/api/tasks/cards",
        headers={**headers, "Content-Type": "application/json"},
        json={"list_uuid": str(a), "title": "Moverme"},
    )
    assert create.status_code == 201, create.text
    card_id = create.json()["uuid"]

    patch = await client.patch(
        f"/api/tasks/cards/{card_id}",
        headers={**headers, "Content-Type": "application/json"},
        json={"list_uuid": str(b), "position": 0},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["list_uuid"] == b


@pytest.mark.asyncio
async def test_task_board_coordinator_can_create_card(client, auth_headers_async: dict[str, str]):
    board = await client.get("/api/tasks/board", headers=auth_headers_async)
    assert board.status_code == 200
    list_uuid = board.json()["lists"][0]["uuid"]
    create = await client.post(
        "/api/tasks/cards",
        headers={**auth_headers_async, "Content-Type": "application/json"},
        json={"list_uuid": str(list_uuid), "title": "Tarjeta coordinador"},
    )
    assert create.status_code == 201, create.text
