from fastapi import APIRouter

from orderflow_api.api.routes.advocates import router as advocates_router
from orderflow_api.api.routes.auth import router as auth_router
from orderflow_api.api.routes.cases import router as cases_router
from orderflow_api.api.routes.documents import router as documents_router
from orderflow_api.api.routes.exports import router as exports_router
from orderflow_api.api.routes.extractions import router as extractions_router
from orderflow_api.api.routes.health import router as health_router
from orderflow_api.api.routes.obligations import router as obligations_router
from orderflow_api.api.routes.proofs import router as proofs_router
from orderflow_api.api.routes.routing import router as routing_router
from orderflow_api.api.routes.departments import router as departments_router
from orderflow_api.api.routes.public import router as public_router
from orderflow_api.api.routes.users import router as users_router
from orderflow_api.api.routes.webhooks import router as webhooks_router
from orderflow_api.api.routes.page_summaries import router as page_summaries_router
from orderflow_api.api.routes.page_annotations import router as page_annotations_router
from orderflow_api.api.routes.workflows import router as workflows_router
from orderflow_api.api.routes.intelligence import router as intelligence_router
from orderflow_api.api.routes.workbench import router as workbench_router
from orderflow_api.api.routes.ai_chat import router as ai_chat_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(advocates_router)
api_router.include_router(cases_router)
api_router.include_router(documents_router)
api_router.include_router(exports_router)
api_router.include_router(extractions_router)
api_router.include_router(obligations_router)
api_router.include_router(proofs_router)
api_router.include_router(routing_router)
api_router.include_router(departments_router)
api_router.include_router(public_router)
api_router.include_router(webhooks_router)
api_router.include_router(page_summaries_router)
api_router.include_router(page_annotations_router)
api_router.include_router(workflows_router)
api_router.include_router(intelligence_router)
api_router.include_router(workbench_router)
api_router.include_router(ai_chat_router)
