from aiogram import Router

from . import editor, errors, fallback, inputs, start, subscription

# Порядок важен: команды (start) должны сработать раньше текстового ввода (inputs),
# а fallback ловит всё остальное и поэтому идёт последним.
router = Router(name="root")
router.include_routers(
    errors.router,
    start.router,
    subscription.router,
    editor.router,
    inputs.router,
    fallback.router,
)

__all__ = ["router"]
