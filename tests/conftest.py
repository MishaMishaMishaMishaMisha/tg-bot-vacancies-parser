import pytest_asyncio
import pytest

from sqlalchemy import text

from src.db.db_connection import async_engine
from src.core.config import settings


# проверка test mode и на успешное подключение к бд
@pytest_asyncio.fixture(scope="session", autouse=True)
async def check_mode_and_db():
    
    try:
        if settings.MODE != "TEST":
            raise TypeError("MODE is not TEST")
        
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            if result.scalar() != 1:
                raise RuntimeError("SELECT 1 returned unexpected result")
        
    except Exception as e:
        pytest.exit(f"Error in check fixture. Text: {e}")
        