from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, links
from app.api.links import redirect_to_original
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models.user import User
from app.services.cache_service import close_redis
from app.utils.security import get_password_hash

Base.metadata.create_all(bind=engine)

settings = get_settings()

app = FastAPI(
    title="URL Shortener API",
    description="Сервис для сокращения ссылок с аналитикой",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(links.router, prefix="/api/links", tags=["Links"])
app.add_api_route(
    "/{short_code}",
    redirect_to_original,
    methods=["GET"],
    include_in_schema=False,
)


def create_admin_user() -> None:
    """Создать администратора из .env если его ещё нет"""
    if not all([
        settings.ADMIN_USERNAME,
        settings.ADMIN_EMAIL,
        settings.ADMIN_PASSWORD,
    ]):
        return

    db = SessionLocal()
    try:
        exists = db.query(User).filter(
            User.username == settings.ADMIN_USERNAME
        ).first()
        if exists:
            return

        admin = User(
            username=settings.ADMIN_USERNAME,
            email=settings.ADMIN_EMAIL,
            hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        db.commit()
        print(f"Admin user '{settings.ADMIN_USERNAME}' created")
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    create_admin_user()
    print("URL Shortener API started")


@app.on_event("shutdown")
async def shutdown_event():
    await close_redis()
    print("URL Shortener API stopped")


@app.get("/")
async def root():
    return {
        "message": "URL Shortener API",
        "docs": "/docs",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
