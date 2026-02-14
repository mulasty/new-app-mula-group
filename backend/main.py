from fastapi import FastAPI

from app.core.config import settings
from app.domain import models  # noqa: F401
from app.infrastructure.db.base import Base
from app.infrastructure.db.session import engine
from app.interfaces.api.router import api_router

app = FastAPI(title=settings.app_name)
app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
