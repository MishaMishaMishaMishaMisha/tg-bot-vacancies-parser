from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.jobs_parsing.models import Vacancy as DomainVacancy
from src.db.models.base import utcnow
from ..models import VacancyModel
from .base import BaseRepository


@dataclass(slots=True)
class UpsertResult:
    new: list[VacancyModel] = field(default_factory=list)       # раньше бот их не видел
    existing: list[VacancyModel] = field(default_factory=list)  # уже были в базе


class VacancyRepository(BaseRepository[VacancyModel]):
    model = VacancyModel
    CHUNK = 500  # строк в одном INSERT (у asyncpg есть лимит на число параметров запроса)

    # ---- чтение ----------------------------------------------------------------

    async def get_by_external_id(self, source: str, external_id: str) -> VacancyModel | None:
        stmt = select(VacancyModel).where(
            VacancyModel.source == source, VacancyModel.external_id == external_id
        )
        return await self.session.scalar(stmt)

    async def get_by_keys(self, keys: Sequence[tuple[str, str]]) -> Sequence[VacancyModel]:
        """Вакансии по парам (source, external_id)."""
        if not keys:
            return []
        stmt = select(VacancyModel).where(
            tuple_(VacancyModel.source, VacancyModel.external_id).in_(list(keys))
        )
        return (await self.session.scalars(stmt)).all()

    async def known_external_ids(self, source: str, external_ids: Iterable[str]) -> set[str]:
        """Какие из этих id уже есть в базе (например, чтобы понять, что в выдаче всё новое)."""
        ids = list(external_ids)
        if not ids:
            return set()
        stmt = select(VacancyModel.external_id).where(
            VacancyModel.source == source, VacancyModel.external_id.in_(ids)
        )
        return set((await self.session.scalars(stmt)).all())

    async def list_recent(self, source: str | None = None, *, limit: int = 50) -> Sequence[VacancyModel]:
        stmt = select(VacancyModel).order_by(VacancyModel.first_seen_at.desc(), VacancyModel.id.desc())
        if source is not None:
            stmt = stmt.where(VacancyModel.source == source)
        return (await self.session.scalars(stmt.limit(limit))).all()

    async def count_by_source(self, *, only_active: bool = True) -> dict[str, int]:
        stmt = select(VacancyModel.source, func.count()).group_by(VacancyModel.source)
        if only_active:
            stmt = stmt.where(VacancyModel.is_active.is_(True))
        return {source: n for source, n in (await self.session.execute(stmt)).all()}

    # ---- запись ----------------------------------------------------------------

    async def upsert_many(self, vacancies: Sequence[DomainVacancy]) -> UpsertResult:
        """Сохраняет вакансии из выдачи сайта и говорит, какие из них новые.

        Новые вставляются; у уже известных обновляется last_seen_at, и они снова
        становятся активными. Остальные поля существующих вакансий не меняются.
        Дубликаты внутри самой пачки схлопываются.
        """
        unique = {(v.source, v.id): v for v in vacancies}
        keys = list(unique)
        result = UpsertResult()

        for start in range(0, len(keys), self.CHUNK):
            chunk_keys = keys[start:start + self.CHUNK]
            rows = [self._to_row(unique[k]) for k in chunk_keys]

            insert_stmt = (
                pg_insert(VacancyModel)
                .values(rows)
                .on_conflict_do_nothing(index_elements=[VacancyModel.source, VacancyModel.external_id])
                .returning(VacancyModel.id)
            )
            # RETURNING отдаёт только реально вставленные строки, то есть новые.
            new_ids = set((await self.session.scalars(insert_stmt)).all())

            key_filter = tuple_(VacancyModel.source, VacancyModel.external_id).in_(chunk_keys)
            await self.session.execute(
                update(VacancyModel)
                .where(key_filter, VacancyModel.id.not_in(list(new_ids)))
                .values(last_seen_at=utcnow(), is_active=True, closed_at=None)
                .execution_options(synchronize_session=False)
            )

            models = await self.session.scalars(
                select(VacancyModel).where(key_filter).execution_options(populate_existing=True)
            )
            for model in models:
                (result.new if model.id in new_ids else result.existing).append(model)
        return result

    async def mark_inactive(self, vacancy_ids: Iterable[UUID]) -> int:
        """Пометить вакансии закрытыми. Возвращает, сколько строк изменено."""
        ids = list(vacancy_ids)
        if not ids:
            return 0
        stmt = (
            update(VacancyModel)
            .where(VacancyModel.id.in_(ids), VacancyModel.is_active.is_(True))
            .values(is_active=False, closed_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        return (await self.session.execute(stmt)).rowcount

    async def get_stale(
        self, source: str, seen_before: datetime, *, limit: int | None = None
    ) -> Sequence[VacancyModel]:
        """Активные вакансии, которых не видели с момента seen_before (кандидаты на закрытие)."""
        stmt = (
            select(VacancyModel)
            .where(
                VacancyModel.source == source,
                VacancyModel.is_active.is_(True),
                VacancyModel.last_seen_at < seen_before,
            )
            .order_by(VacancyModel.last_seen_at)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return (await self.session.scalars(stmt)).all()

    async def delete_closed_before(self, closed_before: datetime) -> int:
        """Удалить давно закрытые вакансии (их уведомления удалятся каскадом)."""
        stmt = delete(VacancyModel).where(
            VacancyModel.is_active.is_(False), VacancyModel.closed_at < closed_before
        )
        return (await self.session.execute(stmt)).rowcount

    @staticmethod
    def _to_row(v: DomainVacancy) -> dict:
        return {
            "source": v.source,
            "external_id": v.id,
            "title": v.title,
            "url": v.url,
            "company": v.company,
            "category": v.category,
            "locations": list(v.locations),
            "salary": v.salary,
            "tags": list(v.tags),
            "description": v.text or None,
            "published_at": v.published,
        }