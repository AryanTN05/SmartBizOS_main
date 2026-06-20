from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from config import settings

DATABASE_URL = settings.database_url

if DATABASE_URL:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True
    )
    SessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
else:
    engine = None
    SessionLocal = None

Base = declarative_base()

async def get_db():
    if not SessionLocal:
        raise Exception("No DATABASE_URL set in environment variables.")
    async with SessionLocal() as session:
        yield session
