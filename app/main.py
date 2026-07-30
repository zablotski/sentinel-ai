import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from app.core.config import configure_observability, is_ci_environment
from app.core.logging_config import configure_logging
from app.agents.graph import activate_checkpointer, deactivate_checkpointer
from app.api.audit import router as audit_router
from app.api.history import router as history_router

configure_observability()
configure_logging()
logger = logging.getLogger("sentinel.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ci = is_ci_environment()
    await activate_checkpointer(is_ci=ci)
    if ci:
        logger.info("Sentinel AI graph ready (CI / MemorySaver)")
    else:
        logger.info("Sentinel AI checkpointer ready")
    yield
    await deactivate_checkpointer()
    logger.info("Sentinel AI checkpointer shut down")


app = FastAPI(title="Sentinel AI - Backend Gatekeeper", lifespan=lifespan)
logger.info("Sentinel AI application initialized")

app.include_router(audit_router, prefix="/api/v1", tags=["Security Audit"])
app.include_router(history_router, prefix="/api/v1", tags=["Audit History"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
