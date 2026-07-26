import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def postgres_session_factory():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    schema = f"test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(url)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(test_engine, expire_on_commit=False)
    finally:
        await test_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_unique_max_user_is_enforced(postgres_session_factory) -> None:
    async with postgres_session_factory() as session:
        session.add_all([User(max_user_id=42), User(max_user_id=42)])
        with pytest.raises(IntegrityError):
            await session.commit()

