from __future__ import annotations

import logging
import os
import re
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from .analyzer import analyze
from .config import AppConfig, ProgramConfig
from .db import Database
from .formatters import format_help, format_list, format_summary
from .parser import RatingClient

log = logging.getLogger(__name__)
router = Router()

CODE_RE = re.compile(r"^\d{5,12}$")

BTN_PROGRAMS = "📚 Программы"
BTN_CODE = "🔢 Мой код"
BTN_HELP = "❓ Помощь"


class EnterCode(StatesGroup):
    waiting = State()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PROGRAMS), KeyboardButton(text=BTN_CODE)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def programs_keyboard(cfg: AppConfig) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=program.button_text, callback_data=f"p:{program.group_id}")]
        for program in cfg.programs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def program_actions(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Я в общем списке", callback_data=f"l:{group_id}:all"),
                InlineKeyboardButton(text="⭐ Среди 1 приоритета", callback_data=f"l:{group_id}:p1"),
            ],
            [
                InlineKeyboardButton(text="📊 Сводка", callback_data=f"p:{group_id}"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"r:{group_id}"),
            ],
            [InlineKeyboardButton(text="« К программам", callback_data="programs")],
        ]
    )


def _cfg(data: dict[str, Any]) -> AppConfig:
    return data["cfg"]


def _db(data: dict[str, Any]) -> Database:
    return data["db"]


def _client(data: dict[str, Any]) -> RatingClient:
    return data["client"]


def normalize_code(text: str) -> str | None:
    cleaned = re.sub(r"[\s№#]+", "", text.strip())
    if CODE_RE.fullmatch(cleaned):
        return cleaned
    return None


async def ask_code(message: Message, state: FSMContext, *, first_time: bool) -> None:
    await state.set_state(EnterCode.waiting)
    intro = (
        "Привет! Я помогу посмотреть тебя в конкурсных списках магистратуры ИТМО.\n\n"
        if first_time
        else ""
    )
    await message.answer(
        intro + "Пришлите уникальный код поступающего (цифры с Госуслуг / суперсервиса).\n"
        "Его можно будет изменить командой /code.",
        reply_markup=main_keyboard(),
    )


async def show_programs(target: Message, cfg: AppConfig, code: str) -> None:
    await target.answer(
        f"Код: <code>{code}</code>\nВыберите программу:",
        reply_markup=programs_keyboard(cfg),
    )


async def _safe_edit(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def render_program(
    *,
    message: Message,
    program: ProgramConfig,
    code: str,
    client: RatingClient,
    view: str,
    force: bool = False,
) -> None:
    await _safe_edit(message, "⏳ Загружаю конкурсный список…")
    try:
        rating = await client.fetch(program, force=force)
    except Exception:
        log.exception("Ошибка загрузки списка %s", program.group_id)
        await _safe_edit(
            message,
            "Не удалось загрузить список ИТМО. Попробуйте обновить через минуту.",
            program_actions(program.group_id),
        )
        return

    analysis = analyze(rating, code)
    if view == "all":
        text = format_list(analysis, code, first_priority=False)
    elif view == "p1":
        text = format_list(analysis, code, first_priority=True)
    else:
        text = format_summary(analysis, code, program.name)
    await _safe_edit(message, text, program_actions(program.group_id))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, cfg: AppConfig) -> None:
    await state.clear()
    code = db.get_code(message.from_user.id)
    if not code:
        await ask_code(message, state, first_time=True)
        return
    await message.answer(
        f"Снова привет! Ваш код: <code>{code}</code>\nВыберите программу или смените код.",
        reply_markup=main_keyboard(),
    )
    await show_programs(message, cfg, code)


@router.message(Command("code"))
@router.message(F.text == BTN_CODE)
async def cmd_code(message: Message, state: FSMContext, db: Database) -> None:
    current = db.get_code(message.from_user.id)
    extra = f"\nСейчас сохранён: <code>{current}</code>" if current else ""
    await state.set_state(EnterCode.waiting)
    await message.answer("Пришлите новый уникальный код поступающего." + extra)


@router.message(Command("programs"))
@router.message(F.text == BTN_PROGRAMS)
async def cmd_programs(message: Message, state: FSMContext, db: Database, cfg: AppConfig) -> None:
    code = db.get_code(message.from_user.id)
    if not code:
        await ask_code(message, state, first_time=False)
        return
    await show_programs(message, cfg, code)


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(format_help())


@router.message(StateFilter(EnterCode.waiting))
async def on_code_entered(message: Message, state: FSMContext, db: Database, cfg: AppConfig) -> None:
    if not message.text:
        await message.answer("Пришлите код сообщением из цифр.")
        return
    if message.text.startswith("/"):
        await message.answer("Сначала пришлите код или нажмите /start.")
        return
    code = normalize_code(message.text)
    if not code:
        await message.answer("Код должен состоять из 5–12 цифр. Пример: 2053628")
        return
    db.upsert_code(message.from_user.id, code)
    await state.clear()
    await message.answer(f"Сохранил код <code>{code}</code>.", reply_markup=main_keyboard())
    await show_programs(message, cfg, code)


@router.message(F.text)
async def on_other_text(message: Message, state: FSMContext, db: Database, cfg: AppConfig) -> None:
    maybe_code = normalize_code(message.text or "")
    if maybe_code:
        db.upsert_code(message.from_user.id, maybe_code)
        await state.clear()
        await message.answer(f"Сохранил код <code>{maybe_code}</code>.", reply_markup=main_keyboard())
        await show_programs(message, cfg, maybe_code)
        return
    await message.answer("Выберите действие на клавиатуре или нажмите /help.")


@router.callback_query(F.data == "programs")
async def cb_programs(callback: CallbackQuery, db: Database, cfg: AppConfig) -> None:
    code = db.get_code(callback.from_user.id)
    if not code:
        await callback.answer("Сначала сохраните код", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await _safe_edit(
            callback.message,
            f"Код: <code>{code}</code>\nВыберите программу:",
            programs_keyboard(cfg),
        )


@router.callback_query(F.data.regexp(r"^[prl]:"))
async def cb_program(callback: CallbackQuery, db: Database, cfg: AppConfig, client: RatingClient) -> None:
    code = db.get_code(callback.from_user.id)
    if not code:
        await callback.answer("Сначала сохраните код через /start", show_alert=True)
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return

    parts = callback.data.split(":")
    action = parts[0]
    group_id = int(parts[1])
    program = cfg.program_by_id(group_id)
    if program is None:
        await callback.answer("Программы больше нет в конфиге", show_alert=True)
        return

    view = "summary"
    force = action == "r"
    if action == "l":
        view = parts[2] if len(parts) > 2 else "all"

    await callback.answer("Обновляю…" if force else "")
    await render_program(
        message=callback.message,
        program=program,
        code=code,
        client=client,
        view=view,
        force=force,
    )


async def run_bot() -> None:
    from dotenv import load_dotenv

    from .config import load_config

    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("123456"):
        raise SystemExit("Укажите BOT_TOKEN в файле .env (см. .env.example)")

    cfg = load_config()
    db = Database()
    client = RatingClient(cache_ttl_seconds=cfg.cache_ttl_seconds)
    proxy = os.getenv("TELEGRAM_PROXY", "").strip() or None
    session = AiohttpSession(proxy=proxy)
    bot = Bot(
        token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    try:
        try:
            me = await bot.get_me()
        except Exception as exc:
            raise SystemExit(
                "Нет доступа к api.telegram.org (с этой машины в РФ TCP 443 до Telegram, "
                "как правило, закрыт, даже если ping проходит).\n"
                "В .env укажите прокси, например:\n"
                "  TELEGRAM_PROXY=socks5://127.0.0.1:1080\n"
                "  TELEGRAM_PROXY=http://user:pass@host:8080\n"
                f"Исходная ошибка: {exc}"
            ) from exc
        log.info("Бот @%s запущен%s", me.username, f" через {proxy}" if proxy else "")
        await dp.start_polling(bot, cfg=cfg, db=db, client=client)
    finally:
        await client.aclose()
        await bot.session.close()
