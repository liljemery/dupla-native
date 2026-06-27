from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user, get_workspace_context, require_budget_access
from app.domain.workspace_context import WorkspaceContext
from app.domain.file_discipline import FileIngestStatus
from app.domain.workflow_phase import WorkflowPhase, normalize_workflow_phase
from app.models.architecture_revision import ArchitectureRevisionDecision
from app.models.user import User
from app.schemas.chat import ChatConversationResponse
from app.schemas.price_database import PriceDatabaseFileListResponse, PriceDatabaseFileResponse
from app.schemas.project import ProjectResponse
from app.schemas.project_lifecycle import (
    ArchitectureRevisionCreateRequest,
    ArchitectureRevisionResponse,
    ProjectEventResponse,
    ProjectEventsPageResponse,
    ProjectFileFolderCreateRequest,
    ProjectFileFolderPatchRequest,
    ProjectFileFolderResponse,
    ProjectFilePatchRequest,
    ProjectFileResponse,
    ProjectFilesListResponse,
    ProjectFileSearchResponse,
    ProjectPatchRequest,
    ProjectTransitionRequest,
    PliegoGenerateRequest,
    ReconcileIngestResponse,
    SpecificationsReplaceRequest,
    SubcontractLineCreateRequest,
    SubcontractQuoteCreateRequest,
    SubcontractQuoteResponse,
    TechnicalFindingCreateRequest,
    TechnicalFindingResponse,
    WorkflowMetaPatchRequest,
)
from app.services.chat_service import ChatService
from app.services.price_database_classification_task import run_price_database_classification_task
from app.services.price_database_service import PriceDatabaseService
from app.services.project_file_classification_service import (
    requeue_files_needing_review,
    run_file_classification_task,
)
from app.services.project_lifecycle_service import ProjectLifecycleService

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _parse_target_phase(raw: str) -> WorkflowPhase:
    return normalize_workflow_phase(raw.strip().upper())


def _parse_revision_decision(raw: str) -> ArchitectureRevisionDecision:
    try:
        return ArchitectureRevisionDecision(raw.strip().upper())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision debe ser APPROVED, REJECTED o PARTIAL",
        ) from e


@router.patch("/{project_uuid}", response_model=ProjectResponse, summary="Actualizar metadatos del proyecto")
async def patch_project(
    project_uuid: UUID,
    body: ProjectPatchRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    raw = body.model_dump(exclude_unset=True, mode="json")
    p = await svc.update_project_meta(current, project_uuid, raw)
    await session.commit()
    return ProjectResponse.from_project(p)


@router.post("/{project_uuid}/transitions", response_model=ProjectResponse, summary="Avanzar fase del flujo")
async def post_transition(
    project_uuid: UUID,
    body: ProjectTransitionRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectResponse:
    target = _parse_target_phase(body.target_phase) if body.target_phase else None
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    p = await svc.transition_phase(
        current,
        project_uuid,
        target,
        target_step_uuid=body.target_step_uuid,
    )
    await session.commit()
    return ProjectResponse.from_project(p)


@router.put(
    "/{project_uuid}/specifications",
    response_model=ProjectResponse,
    summary="Guardar pliego de condiciones",
)
async def put_specifications(
    project_uuid: UUID,
    body: SpecificationsReplaceRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    p = await svc.put_specifications(current, project_uuid, body.document)
    await session.commit()
    return ProjectResponse.from_project(p)


@router.post(
    "/{project_uuid}/specifications/generate",
    response_model=ProjectResponse,
    summary="Generar borrador del pliego (autocompletado)",
)
async def post_specifications_generate(
    project_uuid: UUID,
    body: PliegoGenerateRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    p = await svc.generate_business_pliego(current, project_uuid, body.force)
    await session.commit()
    return ProjectResponse.from_project(p)


@router.post(
    "/{project_uuid}/specifications/approve",
    response_model=ProjectResponse,
    summary="Aprobar pliego de condiciones estructurado",
)
async def post_specifications_approve(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    p = await svc.approve_business_pliego(current, project_uuid)
    await session.commit()
    return ProjectResponse.from_project(p)


@router.patch("/{project_uuid}/workflow-meta", response_model=ProjectResponse, summary="Actualizar workflow_meta")
async def patch_workflow_meta(
    project_uuid: UUID,
    body: WorkflowMetaPatchRequest,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    patch: dict = {}
    if body.budget_pipeline is not None:
        patch["budget_pipeline"] = body.budget_pipeline
    p = await svc.patch_workflow_meta(current, project_uuid, patch)
    await session.commit()
    return ProjectResponse.from_project(p)


@router.get("/{project_uuid}/events", response_model=ProjectEventsPageResponse, summary="Historial de eventos (paginado)")
async def get_project_events(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    limit: int = Query(20, ge=1, le=100, description="Tamaño de página (por defecto 20)"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
    event_type: Optional[str] = Query(None, max_length=80, description="Filtrar por tipo de evento"),
    q: Optional[str] = Query(None, max_length=500, description="Buscar en el payload (JSON) o correo del autor"),
) -> ProjectEventsPageResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rows, total = await svc.list_events_page(
        current,
        project_uuid,
        limit=limit,
        offset=offset,
        event_type=event_type,
        q=q,
    )
    return ProjectEventsPageResponse(
        items=[ProjectEventResponse.from_row(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{project_uuid}/architecture-revisions",
    response_model=ArchitectureRevisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar revisión de arquitectura",
)
async def post_architecture_revision(
    project_uuid: UUID,
    body: ArchitectureRevisionCreateRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ArchitectureRevisionResponse:
    decision = _parse_revision_decision(body.decision)
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rev = await svc.create_architecture_revision(
        current,
        project_uuid,
        decision=decision,
        notes=body.notes,
        checklist=body.checklist,
    )
    await session.commit()
    return ArchitectureRevisionResponse.from_row(rev)


@router.get(
    "/{project_uuid}/architecture-revisions",
    response_model=list[ArchitectureRevisionResponse],
    summary="Listar revisiones de arquitectura",
)
async def get_architecture_revisions(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[ArchitectureRevisionResponse]:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rows = await svc.list_architecture_revisions(current, project_uuid)
    return [ArchitectureRevisionResponse.from_row(r) for r in rows]


@router.get(
    "/{project_uuid}/file-folders",
    response_model=list[ProjectFileFolderResponse],
    summary="Listar carpetas de archivos",
)
async def get_project_file_folders(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    parent_uuid: Annotated[Optional[UUID], Query(description="Omitir para raíz")] = None,
) -> list[ProjectFileFolderResponse]:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rows = await svc.list_file_folders(current, project_uuid, parent_uuid)
    return [ProjectFileFolderResponse.from_row(r) for r in rows]


@router.post(
    "/{project_uuid}/file-folders",
    response_model=ProjectFileFolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear carpeta de archivos",
)
async def post_project_file_folder(
    project_uuid: UUID,
    body: ProjectFileFolderCreateRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectFileFolderResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    row = await svc.create_file_folder(current, project_uuid, body.name, body.parent_uuid)
    await session.commit()
    await session.refresh(row)
    return ProjectFileFolderResponse.from_row(row)


@router.patch(
    "/{project_uuid}/file-folders/{folder_uuid}",
    response_model=ProjectFileFolderResponse,
    summary="Renombrar o mover carpeta",
)
async def patch_project_file_folder(
    project_uuid: UUID,
    folder_uuid: UUID,
    body: ProjectFileFolderPatchRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectFileFolderResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    patch = body.model_dump(exclude_unset=True)
    row = await svc.patch_file_folder(current, project_uuid, folder_uuid, patch)
    await session.commit()
    await session.refresh(row)
    return ProjectFileFolderResponse.from_row(row)


@router.delete(
    "/{project_uuid}/file-folders/{folder_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar carpeta vacía",
)
async def delete_project_file_folder(
    project_uuid: UUID,
    folder_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    await svc.delete_file_folder(current, project_uuid, folder_uuid)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_uuid}/files",
    response_model=ProjectFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir archivo de proyecto",
)
async def post_project_file(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    category: Annotated[Optional[str], Form()] = None,
    folder_uuid: Annotated[Optional[UUID], Form()] = None,
    wizard: Annotated[bool, Form()] = False,
) -> ProjectFileResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    row = await svc.upload_file(
        current,
        project_uuid,
        file,
        category,
        folder_uuid=folder_uuid,
        wizard=wizard,
    )
    await session.commit()
    if row.ingest_status == FileIngestStatus.PUBLISHED.value:
        background_tasks.add_task(run_file_classification_task, row.id)
    return ProjectFileResponse.from_row(row)


@router.get("/{project_uuid}/files", response_model=ProjectFilesListResponse, summary="Listar archivos (paginado)")
async def get_project_files(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    folder_uuid: Annotated[Optional[UUID], Query(description="Omitir para raíz del proyecto")] = None,
    limit: Annotated[int, Query(le=50, ge=1, description="Máximo 50 por página")] = 50,
    offset: Annotated[int, Query(ge=0, description="Desplazamiento")] = 0,
) -> ProjectFilesListResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rows, total = await svc.list_files(
        current, project_uuid, folder_uuid, limit=limit, offset=offset
    )
    return ProjectFilesListResponse(
        items=[ProjectFileResponse.from_row(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{project_uuid}/files/reconcile-ingest",
    response_model=ReconcileIngestResponse,
    summary="Revisar archivos sin clasificar o sin vínculo en pliego GA-FO",
)
async def reconcile_project_files_ingest(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ReconcileIngestResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    await svc.count_all_project_files(current, project_uuid)
    queued = await requeue_files_needing_review(project_id=project_uuid)
    return ReconcileIngestResponse(queued=queued)


@router.get(
    "/{project_uuid}/files/search",
    response_model=list[ProjectFileSearchResponse],
    summary="Buscar archivos en todo el proyecto",
    description="Filtra por texto (nombre o descripción) y/o disciplina. Cada resultado incluye la ruta desde Raíz.",
)
async def search_project_files(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    q: Annotated[Optional[str], Query(description="Texto en nombre o descripción")] = None,
    discipline: Annotated[Optional[str], Query(description="Disciplina (slug)")] = None,
) -> list[ProjectFileSearchResponse]:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    pairs = await svc.search_project_files(current, project_uuid, q, discipline)
    return [ProjectFileSearchResponse.from_row_with_path(pf, path) for pf, path in pairs]


@router.patch(
    "/{project_uuid}/files/{file_uuid}",
    response_model=ProjectFileResponse,
    summary="Actualizar metadatos de archivo",
)
async def patch_project_file(
    project_uuid: UUID,
    file_uuid: UUID,
    body: ProjectFilePatchRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    background_tasks: BackgroundTasks,
) -> ProjectFileResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    patch = body.model_dump(exclude_unset=True)
    row = await svc.patch_project_file(current, project_uuid, file_uuid, patch)
    await session.commit()
    await session.refresh(row)
    ing = patch.get("ingest_status")
    if ing is not None and str(ing).strip().upper() == FileIngestStatus.PUBLISHED.value:
        skip_folder = "folder_uuid" in patch
        background_tasks.add_task(run_file_classification_task, row.id, skip_folder_assign=skip_folder)
    return ProjectFileResponse.from_row(row)


@router.delete(
    "/{project_uuid}/files/{file_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar archivo",
)
async def delete_project_file(
    project_uuid: UUID,
    file_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    await svc.delete_project_file(current, project_uuid, file_uuid)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_uuid}/files/{file_uuid}/download", summary="Descargar archivo")
async def download_project_file(
    project_uuid: UUID,
    file_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> FileResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    pf, path = await svc.get_file_path(current, project_uuid, file_uuid)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado en disco")
    return FileResponse(
        path=str(path),
        filename=pf.original_name,
        media_type=pf.mime or "application/octet-stream",
    )


@router.get(
    "/{project_uuid}/subcontracts",
    response_model=list[SubcontractQuoteResponse],
    summary="Cotizaciones de subcontratación",
)
async def get_subcontracts(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[SubcontractQuoteResponse]:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rows = await svc.list_subcontract_quotes(current, project_uuid)
    return [SubcontractQuoteResponse.from_row(r) for r in rows]


@router.post(
    "/{project_uuid}/subcontracts",
    response_model=SubcontractQuoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear cotización",
)
async def post_subcontract_quote(
    project_uuid: UUID,
    body: SubcontractQuoteCreateRequest,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> SubcontractQuoteResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    q = await svc.create_subcontract_quote(current, project_uuid, body.title)
    await session.commit()
    await session.refresh(q, ["lines"])
    return SubcontractQuoteResponse.from_row(q)


@router.post(
    "/{project_uuid}/subcontracts/{quote_uuid}/lines",
    response_model=SubcontractQuoteResponse,
    summary="Agregar línea a cotización",
)
async def post_subcontract_line(
    project_uuid: UUID,
    quote_uuid: UUID,
    body: SubcontractLineCreateRequest,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> SubcontractQuoteResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    await svc.add_subcontract_line(
        current,
        project_uuid,
        quote_uuid,
        item_label=body.item_label,
        provider=body.provider,
        price=body.price,
        currency=body.currency,
        external_ref=body.external_ref,
    )
    await session.commit()
    row = await svc.get_subcontract_quote_with_lines(current, project_uuid, quote_uuid)
    return SubcontractQuoteResponse.from_row(row)


@router.delete("/{project_uuid}/subcontracts/{quote_uuid}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar cotización")
async def delete_subcontract_quote(
    project_uuid: UUID,
    quote_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    await svc.delete_subcontract_quote(current, project_uuid, quote_uuid)
    await session.commit()


@router.get(
    "/{project_uuid}/technical-findings",
    response_model=list[TechnicalFindingResponse],
    summary="Hallazgos técnicos (registro manual / futuro pipeline IA)",
)
async def list_technical_findings(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[TechnicalFindingResponse]:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    rows = await svc.list_technical_findings(current, project_uuid)
    return [TechnicalFindingResponse.from_row(r) for r in rows]


@router.post(
    "/{project_uuid}/technical-findings",
    response_model=TechnicalFindingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar hallazgo técnico",
)
async def create_technical_finding(
    project_uuid: UUID,
    body: TechnicalFindingCreateRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> TechnicalFindingResponse:
    svc = ProjectLifecycleService(session, ws_ctx.workspace_id)
    row = await svc.create_technical_finding(
        current,
        project_uuid,
        discipline=body.discipline,
        severity=body.severity,
        title=body.title,
        description=body.description,
        evidence_ref=body.evidence_ref,
    )
    await session.commit()
    return TechnicalFindingResponse.from_row(row)


@router.post(
    "/{project_uuid}/chat/conversation",
    response_model=ChatConversationResponse,
    summary="Abrir u obtener chat del proyecto",
)
async def post_project_chat_conversation(
    project_uuid: UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ChatConversationResponse:
    chat = ChatService(session, ws_ctx.workspace_id)
    res = await chat.get_or_create_project_conversation(current, project_uuid)
    await session.commit()
    return res


@router.get(
    "/{project_uuid}/price-database/files",
    response_model=PriceDatabaseFileListResponse,
    summary="Listar archivos de base de precios del proyecto",
)
async def list_price_database_files(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> PriceDatabaseFileListResponse:
    svc = PriceDatabaseService(session, ws_ctx.workspace_id)
    rows = await svc.list_files(current, project_uuid)
    return PriceDatabaseFileListResponse(items=[PriceDatabaseFileResponse.from_row(r) for r in rows])


@router.post(
    "/{project_uuid}/price-database/files",
    response_model=PriceDatabaseFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir archivo de base de precios (PDF / Excel / CSV)",
)
async def post_price_database_file(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
) -> PriceDatabaseFileResponse:
    svc = PriceDatabaseService(session, ws_ctx.workspace_id)
    row = await svc.upload_file(current, project_uuid, file)
    await session.commit()
    background_tasks.add_task(run_price_database_classification_task, row.id)
    return PriceDatabaseFileResponse.from_row(row)


@router.delete(
    "/{project_uuid}/price-database/files/{file_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar archivo de base de precios",
)
async def delete_price_database_file(
    project_uuid: UUID,
    file_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> Response:
    svc = PriceDatabaseService(session, ws_ctx.workspace_id)
    await svc.delete_file(current, project_uuid, file_uuid)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_uuid}/price-database/apply",
    response_model=ProjectResponse,
    summary="Confirmar uso de la base de precios activa en presupuestos",
)
async def post_price_database_apply(
    project_uuid: UUID,
    current: Annotated[User, Depends(require_budget_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ws_ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ProjectResponse:
    svc = PriceDatabaseService(session, ws_ctx.workspace_id)
    project = await svc.confirm_apply(current, project_uuid)
    await session.commit()
    await session.refresh(project)
    return ProjectResponse.from_project(project)
