import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes import (
    admin,
    ai_assistant,
    aps_viewer,
    auth,
    budget,
    chat,
    clash,
    clash_viewer,
    clash_workflow,
    dashboard,
    health,
    modules,
    project_lifecycle,
    projects,
    tasks,
    users,
    workflow_templates,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("ezdxf").setLevel(logging.ERROR)
    from app.services.project_file_classification_service import requeue_pending_discipline_classifications

    await requeue_pending_discipline_classifications()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Grupo Dupla — Arquitectura API",
        description=(
            "**Auth:** `POST /api/auth/token` with form fields `username` (email) and `password`. "
            "Use **Authorize** in Swagger with `Bearer <access_token>`."
        ),
        version="0.1.0",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(ai_assistant.router)
    app.include_router(modules.router)
    app.include_router(projects.router)
    app.include_router(budget.router)
    app.include_router(clash.router)
    app.include_router(clash_workflow.router)
    app.include_router(aps_viewer.router)
    app.include_router(clash_viewer.router)
    app.include_router(workflow_templates.router)
    app.include_router(project_lifecycle.router)
    app.include_router(admin.router)
    app.include_router(dashboard.router)
    app.include_router(chat.router)
    app.include_router(tasks.router)
    app.include_router(health.router)
    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
