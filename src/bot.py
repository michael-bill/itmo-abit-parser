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
from .catalog import filter_families, merge_catalog
from .config import AppConfig, ProgramConfig
from .db import Database
from .formatters import format_faq, format_list, format_summary
from .parser import RatingClient

log = logging.getLogger(__name__)
router = Router()

CODE_RE = re.compile(r"^\d{5,12}$")

BTN_PROGRAMS = "📚 Программы"
BTN_CODE = "🔢 Мой код"
BTN_FAQ = "❓ FAQ"
BTN_HELP = "❓ Помощь"
CATALOG_PAGE_SIZE = 8


class EnterCode(StatesGroup):
    waiting = State()


class BrowseCatalog(StatesGroup):
    searching = State()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PROGRAMS), KeyboardButton(text=BTN_CODE)],
            [KeyboardButton(text=BTN_FAQ)],
        ],
        resize_keyboard=True,
    )


def _family_rows(families: tuple[tuple[ProgramConfig, ...], ...]) -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=family[0].menu_text,
                callback_data=f"f:{family[0].group_id}",
            )
        ]
        for family in families
    ]


def programs_keyboard(cfg: AppConfig) -> InlineKeyboardMarkup:
    rows = _family_rows(cfg.pinned_families())
    if cfg.load_all_programs:
        rows.append([InlineKeyboardButton(text="🔎 Все программы", callback_data="cat")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_keyboard(
    families: tuple[tuple[ProgramConfig, ...], ...],
    *,
    page: int,
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(families) + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CATALOG_PAGE_SIZE
    chunk = families[start : start + CATALOG_PAGE_SIZE]
    rows = _family_rows(chunk)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="←", callback_data=f"cat:p:{page - 1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="cat:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"cat:p:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="« К избранным", callback_data="programs")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def financing_keyboard(family: tuple[ProgramConfig, ...]) -> InlineKeyboardMarkup:
    choices = [
        InlineKeyboardButton(
            text=program.financing_label.capitalize(),
            callback_data=f"p:{program.ref}",
        )
        for program in family
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            choices,
            [InlineKeyboardButton(text="« К программам", callback_data="programs")],
        ]
    )


def program_actions(program: ProgramConfig, cfg: AppConfig) -> InlineKeyboardMarkup:
    ref = program.ref
    family = cfg.family_by_group_id(program.group_id)
    back_data = f"f:{program.group_id}" if len(family) > 1 else "programs"
    back_text = "« К выбору списка" if len(family) > 1 else "« К программам"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Я в общем списке", callback_data=f"l:{ref}:all"),
                InlineKeyboardButton(text="⭐ Среди 1 приоритета", callback_data=f"l:{ref}:p1"),
            ],
            [
                InlineKeyboardButton(text="📊 Сводка", callback_data=f"p:{ref}"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"r:{ref}"),
            ],
            [
                InlineKeyboardButton(text=back_text, callback_data=back_data),
                InlineKeyboardButton(text="❓ FAQ", callback_data="faq"),
            ],
        ]
    )


def faq_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Бот", callback_data="faq:bot"),
                InlineKeyboardButton(text="Сводка", callback_data="faq:summary"),
            ],
            [
                InlineKeyboardButton(text="Бюджет", callback_data="faq:budget"),
                InlineKeyboardButton(text="Платное", callback_data="faq:paid"),
            ],
            [
                InlineKeyboardButton(text="Цвета", callback_data="faq:colors"),
                InlineKeyboardButton(text="Ранжирование", callback_data="faq:rank"),
            ],
            [InlineKeyboardButton(text="Сроки 2026", callback_data="faq:dates")],
            [InlineKeyboardButton(text="« К темам", callback_data="faq:home")],
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


def _catalog_text(code: str, families: tuple[tuple[ProgramConfig, ...], ...], query: str) -> str:
    lines = [f"Код: <code>{code}</code>"]
    if query:
        lines.append(f"Поиск: <code>{query}</code>  ·  найдено {len(families)}")
    else:
        lines.append(f"Все программы магистратуры: {len(families)}")
    lines.append("Напишите название или код, например <code>веб</code> или <code>09.04.04</code>.")
    return "\n".join(lines)


async def show_programs(target: Message, cfg: AppConfig, code: str) -> None:
    extra = "\nИли откройте все программы и найдите по названию." if cfg.load_all_programs else ""
    await target.answer(
        f"Код: <code>{code}</code>\nВыберите программу:{extra}",
        reply_markup=programs_keyboard(cfg),
    )


async def _safe_edit(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def show_financing(message: Message, family: tuple[ProgramConfig, ...], code: str) -> None:
    first = family[0]
    await _safe_edit(
        message,
        f"Код: <code>{code}</code>\n<b>{first.menu_text}</b>\nВыберите список:",
        financing_keyboard(family),
    )


async def render_program(
    *,
    message: Message,
    program: ProgramConfig,
    code: str,
    client: RatingClient,
    cfg: AppConfig,
    view: str,
    force: bool = False,
) -> None:
    await _safe_edit(message, "⏳ Загружаю конкурсный список…")
    try:
        rating = await client.fetch(program, force=force)
    except Exception:
        log.exception("Ошибка загрузки списка %s", program.ref)
        await _safe_edit(
            message,
            "Не удалось загрузить список ИТМО. Попробуйте обновить через минуту.",
            program_actions(program, cfg),
        )
        return

    analysis = analyze(rating, code)
    if view == "all":
        text = format_list(analysis, code, first_priority=False)
    elif view == "p1":
        text = format_list(analysis, code, first_priority=True)
    else:
        text = format_summary(analysis, code, program.name)
    await _safe_edit(message, text, program_actions(program, cfg))


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
    await state.set_state(None)
    await state.update_data(catalog_query="")
    code = db.get_code(message.from_user.id)
    if not code:
        await ask_code(message, state, first_time=False)
        return
    await show_programs(message, cfg, code)


@router.message(Command("help"))
@router.message(Command("faq"))
@router.message(F.text == BTN_FAQ)
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(format_faq(), reply_markup=faq_keyboard(), disable_web_page_preview=True)


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
    saved_code = db.get_code(message.from_user.id)
    query = (message.text or "").strip()
    if query and saved_code and cfg.load_all_programs:
        await state.set_state(BrowseCatalog.searching)
        await state.update_data(catalog_query=query)
        families = filter_families(cfg.families(), query)
        await message.answer(
            _catalog_text(saved_code, families, query),
            reply_markup=catalog_keyboard(families, page=0),
        )
        return
    await message.answer("Выберите действие на клавиатуре или нажмите /faq.")


@router.callback_query(F.data == "faq")
async def cb_faq_open(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            format_faq(),
            reply_markup=faq_keyboard(),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data.regexp(r"^faq:"))
async def cb_faq_topic(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data or not callback.message:
        return
    topic = callback.data.split(":", 1)[1]
    if topic == "home":
        topic = None
    await _safe_edit(callback.message, format_faq(topic), faq_keyboard())


@router.callback_query(F.data == "cat:noop")
async def cb_catalog_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.regexp(r"^cat"))
async def cb_catalog(callback: CallbackQuery, state: FSMContext, db: Database, cfg: AppConfig) -> None:
    code = db.get_code(callback.from_user.id)
    if not code:
        await callback.answer("Сначала сохраните код", show_alert=True)
        return
    if not callback.message:
        await callback.answer()
        return
    page = 0
    if callback.data and callback.data.startswith("cat:p:"):
        try:
            page = int(callback.data.split(":")[2])
        except (IndexError, ValueError):
            page = 0
    data = await state.get_data()
    query = str(data.get("catalog_query") or "")
    await state.set_state(BrowseCatalog.searching)
    families = filter_families(cfg.families(), query)
    await callback.answer()
    await _safe_edit(
        callback.message,
        _catalog_text(code, families, query),
        catalog_keyboard(families, page=page),
    )


@router.callback_query(F.data == "programs")
async def cb_programs(callback: CallbackQuery, state: FSMContext, db: Database, cfg: AppConfig) -> None:
    code = db.get_code(callback.from_user.id)
    if not code:
        await callback.answer("Сначала сохраните код", show_alert=True)
        return
    await state.set_state(None)
    await state.update_data(catalog_query="")
    await callback.answer()
    if callback.message:
        await _safe_edit(
            callback.message,
            f"Код: <code>{code}</code>\nВыберите программу:",
            programs_keyboard(cfg),
        )


@router.callback_query(F.data.regexp(r"^f:\d+$"))
async def cb_family(callback: CallbackQuery, db: Database, cfg: AppConfig, client: RatingClient) -> None:
    code = db.get_code(callback.from_user.id)
    if not code:
        await callback.answer("Сначала сохраните код", show_alert=True)
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    group_id = int(callback.data.split(":")[1])
    family = cfg.family_by_group_id(group_id)
    if not family:
        await callback.answer("Программы больше нет в конфиге", show_alert=True)
        return
    await callback.answer()
    if len(family) == 1:
        await render_program(
            message=callback.message,
            program=family[0],
            code=code,
            client=client,
            cfg=cfg,
            view="summary",
        )
        return
    await show_financing(callback.message, family, code)


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
    if len(parts) < 3:
        await callback.answer("Выберите программу заново", show_alert=True)
        return
    financing = parts[1]
    try:
        group_id = int(parts[2])
    except ValueError:
        await callback.answer("Выберите программу заново", show_alert=True)
        return
    program = cfg.program_by_ref(financing, group_id)
    if program is None:
        await callback.answer("Программы больше нет в конфиге", show_alert=True)
        return

    view = "summary"
    force = action == "r"
    if action == "l":
        view = parts[3] if len(parts) > 3 else "all"

    await callback.answer("Обновляю…" if force else "")
    await render_program(
        message=callback.message,
        program=program,
        code=code,
        client=client,
        cfg=cfg,
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
    if cfg.load_all_programs:
        try:
            catalog = await client.fetch_catalog()
            cfg = cfg.with_programs(merge_catalog(cfg.programs, catalog))
            log.info("Каталог программ: %s списков, %s направлений", len(cfg.programs), len(cfg.families()))
        except Exception:
            log.exception("Не удалось загрузить каталог программ, остаются записи из config.yaml")
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
