from __future__ import annotations

import logging
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .catalog import catalog_from_items
from .config import ProgramConfig
from .models import Applicant, ProgramRating

log = logging.getLogger(__name__)

ABIT_ORIGIN = "https://abit.itmo.ru"
ABITLK_ORIGIN = "https://abitlk.itmo.ru"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
BUILD_ID_RE = re.compile(r"/_next/static/([A-Za-z0-9_-]+)/_buildManifest\.js")
MSK = timezone(timedelta(hours=3))
NO_CACHE_HEADERS = {"Cache-Control": "no-cache", "Pragma": "no-cache"}


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_update_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_applicant(raw: dict[str, Any], quota: str) -> Applicant:
    sspvo = str(raw.get("sspvo_id") or "").strip()
    return Applicant(
        sspvo_id=sspvo,
        position=int(raw.get("position") or 0),
        priority=_to_int_or_none(raw.get("priority")),
        contest=(str(raw["contest"]).strip() if raw.get("contest") else None),
        exam_type=(str(raw["exam_type"]).strip() if raw.get("exam_type") else None),
        ia_scores=_to_float(raw.get("ia_scores")),
        exam_scores=_to_float(raw.get("exam_scores")),
        total_scores=_to_float(raw.get("total_scores")),
        diploma_average=_to_float_or_none(raw.get("diploma_average")),
        is_send_agreement=bool(raw.get("is_send_agreement")),
        has_approved_contract=bool(raw.get("has_approved_contract")),
        has_paid_contract=bool(raw.get("has_paid_contract")),
        status=(str(raw["status"]) if raw.get("status") else None),
        main_top_priority=bool(raw.get("main_top_priority")),
        highest_passageway_priority=bool(raw.get("highest_passageway_priority")),
        quota=quota,
    )


def parse_program_list(payload: dict[str, Any], source_url: str, financing: str) -> ProgramRating:
    direction = payload.get("direction") or {}
    raw_list = payload.get("general_competition") or payload.get("items") or []
    general = tuple(
        _parse_applicant(item, "general")
        for item in raw_list
        if isinstance(item, dict)
    )
    target = tuple(
        _parse_applicant(item, "target")
        for item in (payload.get("by_target_quota") or [])
        if isinstance(item, dict)
    )
    return ProgramRating(
        title=str(direction.get("direction_title") or "Программа").strip(),
        competitive_group_id=int(direction.get("competitive_group_id") or 0),
        financing=financing,
        budget_places=int(direction.get("budget_min") or 0),
        contract_places=int(direction.get("contract") or 0),
        target_places=int(direction.get("target_reception") or 0),
        update_time=_parse_update_time(payload.get("update_time")),
        fetched_at=datetime.now(MSK),
        general=general,
        target_quota=target,
        source_url=source_url,
    )


class RatingClient:
    """Тянет конкурсный список: сначала быстрый Next.js JSON, затем API личного кабинета."""

    def __init__(self, cache_ttl_seconds: int = 45) -> None:
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[str, int], tuple[float, ProgramRating]] = {}
        self._build_id: str | None = None
        self._build_id_at: float = 0.0
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html"},
            timeout=httpx.Timeout(5.0, connect=3.0),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def invalidate(self, group_id: int | None = None) -> None:
        if group_id is None:
            self._cache.clear()
            return
        for key in [key for key in self._cache if key[1] == group_id]:
            self._cache.pop(key, None)

    async def fetch(self, program: ProgramConfig, *, force: bool = False) -> ProgramRating:
        cache_key = (program.financing, program.group_id)
        if not force:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < self.cache_ttl_seconds:
                return cached[1]

        errors: list[str] = []
        loaders = (self._load_abitlk, self._load_next_data) if force else (self._load_next_data, self._load_abitlk)
        for loader in loaders:
            try:
                rating = await loader(program, bust_cache=force)
                rating = replace(rating, fetched_at=datetime.now(MSK))
                self._cache[cache_key] = (time.monotonic(), rating)
                return rating
            except Exception as exc:  # noqa: BLE001 — хотим попробовать второй источник
                log.warning("Не удалось загрузить %s через %s: %s", program.group_id, loader.__name__, exc)
                errors.append(f"{loader.__name__}: {exc}")

        raise RuntimeError("Не удалось загрузить конкурсный список:\n" + "\n".join(errors))

    async def _load_next_data(self, program: ProgramConfig, *, bust_cache: bool = False) -> ProgramRating:
        build_id = await self._get_build_id()
        url = (
            f"{ABIT_ORIGIN}/_next/data/{build_id}/rating/"
            f"{program.degree}/{program.financing}/{program.group_id}.json"
        )
        params = {"_ts": str(int(time.time()))} if bust_cache else None
        headers = NO_CACHE_HEADERS if bust_cache else None
        response = await self._client.get(url, params=params, headers=headers)
        if response.status_code == 404:
            self._build_id = None
            build_id = await self._get_build_id(force=True)
            url = (
                f"{ABIT_ORIGIN}/_next/data/{build_id}/rating/"
                f"{program.degree}/{program.financing}/{program.group_id}.json"
            )
            response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        payload = (data.get("pageProps") or {}).get("programList")
        if not isinstance(payload, dict):
            raise ValueError("В ответе Next.js нет programList")
        return parse_program_list(payload, program.url, program.financing)

    async def _load_abitlk(self, program: ProgramConfig, *, bust_cache: bool = False) -> ProgramRating:
        url = f"{ABITLK_ORIGIN}/api/v1/rating/{program.degree}/{program.financing}"
        params: dict[str, str] = {"competitive_group_id": str(program.group_id)}
        if bust_cache:
            params["_ts"] = str(int(time.time()))
        headers = NO_CACHE_HEADERS if bust_cache else None
        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise ValueError(data.get("message") or "API вернул ok=false")
        payload = data.get("result")
        if not isinstance(payload, dict):
            raise ValueError("В ответе API нет result")
        return parse_program_list(payload, program.url, program.financing)

    async def fetch_catalog(self) -> tuple[ProgramConfig, ...]:
        response = await self._client.get(
            f"{ABITLK_ORIGIN}/api/v1/rating/directions",
            params={"degree": "master"},
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise ValueError(data.get("message") or "API каталога вернул ok=false")
        items = (data.get("result") or {}).get("items") or []
        if not isinstance(items, list) or not items:
            raise ValueError("В каталоге программ пустой список")
        return catalog_from_items(items)

    async def _get_build_id(self, *, force: bool = False) -> str:
        if not force and self._build_id and time.monotonic() - self._build_id_at < 3600:
            return self._build_id
        response = await self._client.get(f"{ABIT_ORIGIN}/ratings/master")
        response.raise_for_status()
        match = BUILD_ID_RE.search(response.text)
        if not match:
            raise ValueError("Не найден Next.js buildId на странице списков")
        self._build_id = match.group(1)
        self._build_id_at = time.monotonic()
        return self._build_id
