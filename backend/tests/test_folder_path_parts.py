"""Tests for in-memory folder path indexing."""

from uuid import uuid4

from app.models.project_file_folder import ProjectFileFolder
from app.services.folder_path_parts import (
    build_folder_children_map,
    build_folder_path_index,
    descendant_folder_ids,
    format_folder_path,
)


def _folder(project_id, name, parent_id=None):
    return ProjectFileFolder(
        id=uuid4(),
        project_id=project_id,
        parent_id=parent_id,
        name=name,
        created_by=uuid4(),
    )


def test_build_folder_path_index_resolves_nested_paths() -> None:
    project_id = uuid4()
    root = _folder(project_id, "PLANOS RECIBIDOS")
    child = _folder(project_id, "TECNICOS", root.id)
    leaf = _folder(project_id, "ELECTRICO", child.id)
    folders = [root, child, leaf]

    paths = build_folder_path_index(folders)
    children = build_folder_children_map(folders)

    assert paths[leaf.id] == ["PLANOS RECIBIDOS", "TECNICOS", "ELECTRICO"]
    assert format_folder_path(paths[leaf.id]) == "Raíz / PLANOS RECIBIDOS / TECNICOS / ELECTRICO"
    assert descendant_folder_ids(root.id, children) == {root.id, child.id, leaf.id}
