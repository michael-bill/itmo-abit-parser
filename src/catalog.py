from __future__ import annotations

import re
from typing import Any

from .config import ProgramConfig

TITLE_RE = re.compile(
    r"^(?P<code>[\d.]+(?:\s+и\s+[\d.]+)*)\s*[«\"](?P<name>.+)[»\"]\s*$"
)
BUTTON_NAME_LIMIT = 36


def parse_direction_title(title: str) -> tuple[str, str]:
    text = title.strip()
    match = TITLE_RE.match(text)
    if match:
        raw_code = match.group("code")
        name = match.group("name").strip()
    else:
        code_match = re.match(r"^([\d.]+)", text)
        raw_code = code_match.group(1) if code_match else ""
        quoted = re.search(r"[«\"](.+)[»\"]", text)
        name = quoted.group(1).strip() if quoted else text
    code = re.match(r"^([\d.]+)", raw_code)
    direction_code = code.group(1) if code else raw_code
    if " / " in name:
        left, right = name.split(" / ", 1)
        name = left if re.search(r"[А-Яа-яЁё]", left) else right
    return direction_code, name


def _shorten(name: str) -> str:
    if len(name) <= BUTTON_NAME_LIMIT:
        return name
    return name[: BUTTON_NAME_LIMIT - 1].rstrip(" ,;/-") + "…"


def program_from_direction(item: dict[str, Any], *, financing: str) -> ProgramConfig:
    title = str(item.get("direction_title") or "").strip()
    group_id = int(item["competitive_group_id"])
    direction_code, name = parse_direction_title(title)
    return ProgramConfig(
        name=name,
        short=_shorten(name),
        direction_code=direction_code or "—",
        url=f"https://abit.itmo.ru/rating/master/{financing}/{group_id}",
        degree="master",
        financing=financing,
        group_id=group_id,
    )


def catalog_from_items(items: list[dict[str, Any]]) -> tuple[ProgramConfig, ...]:
    programs: list[ProgramConfig] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("competitive_group_id"):
            continue
        if int(item.get("budget_min") or 0) > 0:
            programs.append(program_from_direction(item, financing="budget"))
        if int(item.get("contract") or 0) > 0:
            programs.append(program_from_direction(item, financing="contract"))
    return tuple(programs)


def merge_catalog(
    pinned: tuple[ProgramConfig, ...],
    catalog: tuple[ProgramConfig, ...],
) -> tuple[ProgramConfig, ...]:
    by_key = {(program.financing, program.group_id): program for program in catalog}
    for program in pinned:
        by_key[(program.financing, program.group_id)] = program

    pinned_ids: list[int] = []
    seen: set[int] = set()
    for program in pinned:
        if program.group_id not in seen:
            seen.add(program.group_id)
            pinned_ids.append(program.group_id)

    rest_ids = sorted(
        {program.group_id for program in by_key.values() if program.group_id not in seen},
        key=lambda group_id: next(
            program.name for program in by_key.values() if program.group_id == group_id
        ).casefold(),
    )
    result: list[ProgramConfig] = []
    for group_id in pinned_ids + rest_ids:
        for financing in ("budget", "contract", "contract_foreigner"):
            program = by_key.get((financing, group_id))
            if program:
                result.append(program)
    return tuple(result)


def filter_families(
    families: tuple[tuple[ProgramConfig, ...], ...],
    query: str,
) -> tuple[tuple[ProgramConfig, ...], ...]:
    needle = " ".join(query.casefold().split())
    if not needle:
        return families
    result = []
    for family in families:
        first = family[0]
        hay = " ".join(
            [
                first.name,
                first.short,
                first.direction_code,
                str(first.group_id),
            ]
        ).casefold()
        if needle in hay:
            result.append(family)
    return tuple(result)
