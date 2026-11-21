import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import account, chat, jack, workspaces
from .auth import router as auth_router
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.ensure_indexes()
    yield
    await db.close()


app = FastAPI(title="GTM Strategy Agent", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(account.router)
app.include_router(jack.router)
app.include_router(workspaces.router)
app.include_router(chat.router)


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def root():
    """Friendly answer for anyone opening the API address in a browser."""
    return {
        "service": "GTM Strategy Agent API",
        "status": "running",
        "health": "/healthz",
        "note": "This is the backend. Open the web app to use it.",
    }


@app.get("/healthz")
async def healthz():
    return {"ok": True}
