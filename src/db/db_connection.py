from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.core.config import settings


async_engine = create_async_engine(url=settings.db.url)

async_session_factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)

async def get_db():
    async with async_session_factory() as session:
        yield session