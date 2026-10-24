"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.session import init_db, close_db

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting application...")
    await init_db()
    logger.info("Application started")
    yield
    logger.info("Shutting down application...")
    await close_db()
    logger.info("Application stopped")


app = FastAPI(
    title=settings.APP_NAME,
    description="Finance Automation API for contract and installment management",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "health": "/health",
    }


# Import and include routers
# from app.api import contracts, installments, uploads, contacts, notifications, users
# app.include_router(contracts.router, prefix="/api/v1/contracts", tags=["contracts"])
# app.include_router(installments.router, prefix="/api/v1/installments", tags=["installments"])
# app.include_router(uploads.router, prefix="/api/v1/uploads", tags=["uploads"])
# app.include_router(contacts.router, prefix="/api/v1/contacts", tags=["contacts"])
# app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
# app.include_router(users.router, prefix="/api/v1/users", tags=["users"])