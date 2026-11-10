"""Черновик фильтров в состоянии диалога (FSM).
"""
from __future__ import annotations

from dataclasses import asdict

from aiogram.fsm.context import FSMContext

from src.services import SubscriptionFilters


async def load_draft(state: FSMContext) -> SubscriptionFilters | None:
    raw = (await state.get_data()).get("draft")
    return SubscriptionFilters(**raw) if raw else None


async def save_draft(state: FSMContext, draft: SubscriptionFilters) -> None:
    await state.update_data(draft=asdict(draft))
