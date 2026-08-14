from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "bot.db"


@dataclass(frozen=True)
class ProgramConfig:
    name: str
    short: str
    url: str
    degree: str
    financing: str
    group_id: int

    @property
    def button_text(self) -> str:
        return self.short or self.name


@dataclass(frozen=True)
class AppConfig:
    cache_ttl_seconds: int
    programs: tuple[ProgramConfig, ...]

    def program_by_id(self, group_id: int) -> ProgramConfig | None:
        for program in self.programs:
            if program.group_id == group_id:
                return program
        return None


def _parse_rating_url(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    # rating / master / budget / 2379
    try:
        rating_idx = parts.index("rating")
        degree, financing, raw_id = parts[rating_idx + 1 : rating_idx + 4]
        return degree, financing, int(raw_id)
    except (ValueError, IndexError) as exc:
        raise ValueError(
            f"Не удалось разобрать URL программы: {url}. "
            "Ожидается вид https://abit.itmo.ru/rating/master/budget/2379"
        ) from exc


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    programs: list[ProgramConfig] = []
    seen_ids: set[int] = set()
    for item in raw.get("programs") or []:
        url = str(item["url"]).strip()
        degree, financing, group_id = _parse_rating_url(url)
        if group_id in seen_ids:
            raise ValueError(f"Программа {group_id} повторяется в config.yaml")
        seen_ids.add(group_id)
        title = str(item.get("name") or "").strip() or f"Программа {group_id}"
        short = str(item.get("short") or title).strip()
        programs.append(
            ProgramConfig(
                name=title,
                short=short,
                url=url,
                degree=degree,
                financing=financing,
                group_id=group_id,
            )
        )
    if not programs:
        raise ValueError("В config.yaml нет ни одной программы")
    return AppConfig(
        cache_ttl_seconds=int(raw.get("cache_ttl_seconds") or 45),
        programs=tuple(programs),
    )
