from __future__ import annotations

from dataclasses import dataclass

from app.models.user import UserRole


@dataclass(frozen=True, slots=True)
class PermissionDef:
    key: str
    label: str
    category: str


PERMISSION_CATALOG: tuple[PermissionDef, ...] = (
    PermissionDef("admin.access", "Acceso al panel admin", "Admin"),
    PermissionDef("admin.users.list", "Listar usuarios", "Admin"),
    PermissionDef("admin.users.create", "Crear e importar usuarios", "Admin"),
    PermissionDef("admin.users.edit", "Editar usuarios", "Admin"),
    PermissionDef("admin.users.delete", "Eliminar usuarios", "Admin"),
    PermissionDef("admin.workspaces.manage", "Gestionar workspaces", "Admin"),
    PermissionDef("admin.permissions.manage", "Gestionar roles y permisos", "Admin"),
    PermissionDef("dashboard.view", "Ver panel KPIs", "Dashboard"),
    PermissionDef("workflow.templates.manage", "Gestionar flujos de trabajo", "Flujos"),
    PermissionDef("projects.create", "Crear proyectos", "Proyectos"),
    PermissionDef("projects.view_all", "Ver todos los proyectos del workspace", "Proyectos"),
    PermissionDef("budget.view", "Ver presupuesto", "Presupuesto"),
    PermissionDef("budget.edit", "Editar presupuesto", "Presupuesto"),
    PermissionDef("lifecycle.control_review", "Marcar revisión de control", "Ciclo de vida"),
    PermissionDef("lifecycle.approve_specs", "Aprobar especificaciones", "Ciclo de vida"),
    PermissionDef("workspace.access_all", "Acceso a todos los workspaces", "Workspace"),
    PermissionDef("tasks.board.edit", "Editar tablero de tareas", "Tareas"),
    PermissionDef("tasks.board.view_all", "Ver todas las tareas del workspace", "Tareas"),
    PermissionDef("tasks.board.assign", "Asignar tareas a otras personas", "Tareas"),
    PermissionDef("tasks.board.manage", "Configurar columnas del tablero", "Tareas"),
)

ALL_PERMISSION_KEYS: frozenset[str] = frozenset(p.key for p in PERMISSION_CATALOG)

SYSTEM_ROLE_LABELS: dict[str, str] = {
    UserRole.GERENCIA.value: "Gerencia",
    UserRole.CONTROL.value: "Control",
    UserRole.PRESUPUESTO.value: "Presupuesto",
    UserRole.ARQUITECTURA.value: "Arquitectura",
    "TEAM_LEADER": "Líder de equipo",
}

DEFAULT_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    UserRole.GERENCIA.value: ALL_PERMISSION_KEYS,
    "TEAM_LEADER": frozenset(
        {
            "admin.access",
            "admin.users.list",
            "admin.users.edit",
            "admin.users.delete",
            "dashboard.view",
            "workflow.templates.manage",
            "projects.create",
            "projects.view_all",
            "budget.view",
            "budget.edit",
            "lifecycle.control_review",
            "lifecycle.approve_specs",
            "tasks.board.edit",
            "tasks.board.view_all",
            "tasks.board.assign",
            "tasks.board.manage",
        }
    ),
    UserRole.CONTROL.value: frozenset(
        {
            "budget.view",
            "budget.edit",
            "lifecycle.control_review",
            "tasks.board.edit",
        }
    ),
    UserRole.PRESUPUESTO.value: frozenset(
        {
            "budget.view",
            "budget.edit",
        }
    ),
    UserRole.ARQUITECTURA.value: frozenset(
        {
            "lifecycle.approve_specs",
            "tasks.board.edit",
        }
    ),
}

SYSTEM_ROLE_SLUGS: frozenset[str] = frozenset(DEFAULT_ROLE_PERMISSIONS.keys())
