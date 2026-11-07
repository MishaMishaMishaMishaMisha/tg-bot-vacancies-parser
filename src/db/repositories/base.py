"""Базовый репозиторий с CRUD-операциями.

Репозитории не делают commit: они только выполняют запросы и flush, а транзакцией
управляет вызывающий код (сервис), чтобы несколько операций можно было сделать атомарно.
"""
from __future__ import annotations

from typing import Any, Generic, Iterable, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]  # задаётся в наследнике

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- чтение ----------------------------------------------------------------

    async def get(self, id_: UUID) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def get_many(self, ids: Iterable[UUID]) -> Sequence[ModelT]:
        ids = list(ids)
        if not ids:
            return []
        stmt = select(self.model).where(self.model.id.in_(ids))  # type: ignore[attr-defined]
        return (await self.session.scalars(stmt)).all()

    async def get_all(
        self, *, limit: int | None = None, offset: int = 0, order_by: Any = None
    ) -> Sequence[ModelT]:
        stmt = select(self.model)
        stmt = stmt.order_by(order_by if order_by is not None else self.model.id)  # type: ignore[attr-defined]
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return (await self.session.scalars(stmt)).all()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(self.model)) or 0

    async def exists(self, id_: UUID) -> bool:
        stmt = select(self.model.id).where(self.model.id == id_).limit(1)  # type: ignore[attr-defined]
        return (await self.session.scalar(stmt)) is not None

    # ---- запись ----------------------------------------------------------------

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()  # id и значения по умолчанию появляются сразу
        return obj

    async def add_many(self, objs: Iterable[ModelT]) -> list[ModelT]:
        objs = list(objs)
        self.session.add_all(objs)
        await self.session.flush()
        return objs

    async def create(self, **values: Any) -> ModelT:
        return await self.add(self.model(**values))

    async def update(self, obj: ModelT, **values: Any) -> ModelT:
        for key, value in values.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def update_by_id(self, id_: UUID, **values: Any) -> ModelT | None:
        obj = await self.get(id_)
        if obj is None:
            return None
        return await self.update(obj, **values)

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def delete_by_id(self, id_: UUID) -> bool:
        stmt = delete(self.model).where(self.model.id == id_)  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return result.rowcount > 0
    
