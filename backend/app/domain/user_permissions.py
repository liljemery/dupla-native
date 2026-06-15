from app.models.user import User, UserRole


def is_gerencia(user: User) -> bool:
    return user.role == UserRole.GERENCIA


def has_elevated_access(user: User) -> bool:
    return is_gerencia(user) or user.is_team_leader


def can_create_users(user: User) -> bool:
    return is_gerencia(user)


def can_assign_team_leader(user: User) -> bool:
    return is_gerencia(user)


def can_view_budget(user: User) -> bool:
    return user.role != UserRole.ARQUITECTURA
