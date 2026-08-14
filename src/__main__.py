from __future__ import annotations

import argparse
import asyncio
import logging

from .analyzer import analyze
from .config import load_config
from .formatters import format_list, format_summary
from .parser import RatingClient


async def dump(group_id: int | None, code: str) -> None:
    cfg = load_config()
    programs = [p for p in cfg.programs if group_id is None or p.group_id == group_id]
    if not programs:
        raise SystemExit(f"Программа {group_id} не найдена в config.yaml")

    client = RatingClient(cache_ttl_seconds=0)
    try:
        for program in programs:
            rating = await client.fetch(program, force=True)
            analysis = analyze(rating, code)
            print(format_summary(analysis, code, program.name))
            print("\n" + "—" * 40 + "\n")
            print(format_list(analysis, code, first_priority=False))
            print("\n" + "—" * 40 + "\n")
            print(format_list(analysis, code, first_priority=True))
            print("\n" + "=" * 40 + "\n")
    finally:
        await client.aclose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Бот конкурсных списков ИТМО")
    parser.add_argument(
        "--dump",
        nargs="*",
        metavar=("CODE", "PROGRAM_ID"),
        help="Печать сводки без Telegram. Пример: --dump 2053628 2379",
    )
    args = parser.parse_args()
    if args.dump is not None:
        if not args.dump:
            raise SystemExit("Укажите код: python -m src --dump 2053628")
        code = args.dump[0]
        group_id = int(args.dump[1]) if len(args.dump) > 1 else None
        asyncio.run(dump(group_id, code))
        return

    from .bot import run_bot

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
