from __future__ import annotations

import html
from datetime import datetime

from .config import FINANCING_LABELS
from .models import Analysis, Applicant


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def _fmt_score(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.{digits}f}"


def _fmt_diploma(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.4f}"


def _fmt_time(value: datetime | None) -> str:
    if value is None:
        return "неизвестно"
    return value.strftime("%d.%m.%Y, %H:%M")


def _quota_label(person: Applicant) -> str:
    return "целевая квота" if person.quota == "target" else "общий конкурс"


def _status_emoji(person: Applicant, *, paid: bool = False) -> str:
    if paid:
        if person.has_paid_contract:
            return "🟢"
        if person.has_approved_contract:
            return "🟡"
        return "⚪"
    if person.status in ("recommended", "in_order") and person.is_send_agreement:
        return "🟢"
    if person.status == "recommended":
        return "🟡"
    if person.status in ("pass_another", "in_another_order"):
        return "🔘"
    return "⚪"


def _color_label(person: Applicant, *, paid: bool = False) -> str:
    mark = _status_emoji(person, paid=paid)
    if paid:
        if person.has_paid_contract:
            return f"{mark} договор оплачен"
        if person.has_approved_contract:
            return f"{mark} договор есть, оплаты нет"
        return f"{mark} без договора"
    if person.status in ("recommended", "in_order") and person.is_send_agreement:
        return f"{mark} проходите сюда, согласие есть"
    if person.status == "recommended":
        return f"{mark} проходите сюда, согласия нет"
    if person.status in ("pass_another", "in_another_order"):
        return f"{mark} проходите на другую программу"
    return f"{mark} без пометки"


def _person_line(person: Applicant, *, highlight: bool = False, paid: bool = False) -> str:
    mark = "➤ " if highlight else "    "
    you = "  ← вы" if highlight else ""
    diploma = _fmt_diploma(person.diploma_average)
    if paid:
        if person.has_paid_contract:
            agr = "оплачен"
        elif person.has_approved_contract:
            agr = "дог."
        else:
            agr = "без дог."
    else:
        agr = "согл." if person.is_send_agreement else "без согл."
    prio = person.priority if person.priority is not None else "—"
    return (
        f"{mark}{_status_emoji(person, paid=paid)} <b>#{person.position}</b>  №{_esc(person.sspvo_id)}"
        f"  пр.{_esc(prio)}  ВИ+ИД {_fmt_score(person.total_scores, 1)}"
        f"  дип.{diploma}  {agr}{you}"
    )


def _flag(value: bool) -> str:
    return "✅ да" if value else "❌ нет"


def _below_min_exam(person: Applicant) -> bool:
    return person.exam_scores < 50 and person.total_scores < 50


def _verdict(analysis: Analysis) -> str:
    me = analysis.me
    rating = analysis.rating
    places = rating.places
    assert me is not None
    hpp_place = analysis.hpp_place or 0

    if _below_min_exam(me):
        return (
            "Пока вы только в списке подавших документы.\n"
            "В конкурс попадут те, у кого балл ВИ не меньше 50."
        )
    if rating.is_paid:
        in_places = me.position <= places
        if me.has_paid_contract and in_places:
            return (
                f"Договор оплачен, и вы в пределах {places} платных мест.\n"
                "Если оплата сохранится — вас зачислят сюда."
            )
        if me.has_approved_contract and in_places:
            return (
                f"Договор есть, но ещё не оплачен. Вы в пределах {places} платных мест.\n"
                "Без оплаты сюда не зачислят."
            )
        if in_places:
            return (
                f"По месту вы в пределах {places} платных, но договора нет.\n"
                "На платное зачисляют только с договором и оплатой."
            )
        if me.has_contract:
            return (
                f"Договор есть, но вы за чертой: {me.position}-е место "
                f"при {places} платных."
            )
        return (
            f"{me.position}-е место при {places} платных, договора нет.\n"
            "На платное зачисляют по договору и оплате."
        )
    if me.highest_passageway_priority and hpp_place <= places:
        return (
            f"Вас зачислят на эту программу.\n"
            f"Согласие уже есть, и вы в пределах мест: {hpp_place}-й "
            f"из {places} бюджетных."
        )
    if me.highest_passageway_priority and hpp_place > places:
        return (
            f"Согласие на эту программу есть, но вы пока за чертой.\n"
            f"Реальное место {hpp_place} при {places} бюджетных."
        )
    if me.main_top_priority and not me.is_send_agreement:
        return (
            "Сейчас вы проходите на эту программу — это ваш лучший вариант, куда хватает баллов.\n"
            "Согласия ещё нет. Без него место не закрепят: зачислят только после согласия."
        )
    if me.main_top_priority:
        return (
            "Сюда вы проходите, но ИТМО пока не ставит вас в зачисление на эту программу."
        )
    return (
        "Сейчас вас сюда не зачислят.\n"
        "Либо вы проходите на другую программу выше по приоритету, либо пока никуда не проходите."
    )


def format_summary(analysis: Analysis, code: str, program_name: str) -> str:
    rating = analysis.rating
    places = rating.places
    target = rating.target_places
    paid = rating.is_paid
    me = analysis.me
    kind = FINANCING_LABELS.get(rating.financing, rating.financing)
    places_label = f"{places} платных мест" if paid else f"{places} бюджетных мест"

    header = [
        f"🎓 <b>{_esc(rating.title or program_name)}</b>",
        "",
        f"🏛 {kind}  ·  {places_label}" + (f"  ·  {target} целевых" if target and not paid else ""),
        f"🕐 список ИТМО от {_esc(_fmt_time(rating.update_time))}",
        f"🔄 проверено {_esc(_fmt_time(rating.fetched_at))}",
        f'<a href="{_esc(rating.source_url)}">открыть список на сайте</a>',
        "",
        f"🔢 код  <code>{_esc(code)}</code>",
    ]

    if me is None:
        return "\n".join(header + ["", "❌ Этот код в списке не найден."])

    prio = me.priority if me.priority is not None else "—"
    places_block = [
        "",
        "📊 <b>Места</b>",
        f"в общем списке  ·  <b>{me.position}</b> из {analysis.overall_total}",
    ]
    if me.priority == 1 and analysis.prio1_position is not None:
        places_block.append(
            f"среди 1 приоритета  ·  <b>{analysis.prio1_position}</b> из {len(analysis.prio1)}"
        )
    else:
        places_block.append(
            f"ваш приоритет  ·  <b>{_esc(prio)}</b>    среди 1 приоритета здесь {len(analysis.prio1)}"
        )
    if not paid and analysis.hpp_place is not None:
        places_block.append(
            f"реальное по ВПП  ·  <b>{analysis.hpp_place}</b> из {places}"
        )
    elif paid and analysis.agreement_place is not None:
        places_block.append(
            f"среди договоров  ·  <b>{analysis.agreement_place}</b>"
        )

    you_block = [
        "",
        "👤 <b>Вы</b>",
        (
            f"баллы  ·  ВИ {_fmt_score(me.exam_scores, 1)} + ИД {_fmt_score(me.ia_scores, 1)}"
            f" = <b>{_fmt_score(me.total_scores, 1)}</b>"
        ),
        f"диплом  ·  {_fmt_diploma(me.diploma_average)}",
        f"испытание  ·  {_esc(me.exam_label)}",
        f"конкурс  ·  {_esc(_quota_label(me))}",
        (
            f"договор  ·  {_flag(me.has_approved_contract)}"
            f"    оплата  ·  {_flag(me.has_paid_contract)}"
            if paid
            else f"согласие  ·  {_flag(me.is_send_agreement)}"
        ),
        f"пометка ИТМО  ·  {_color_label(me, paid=paid)}",
    ]
    if not paid:
        you_block += [
            f"ОВП  ·  {_flag(me.main_top_priority)}",
            f"ВПП  ·  {_flag(me.highest_passageway_priority)}",
        ]
    you_block += [
        "",
        f"<blockquote>{_esc(_verdict(analysis))}</blockquote>",
    ]

    contest_block: list[str] = []
    if analysis.ahead and analysis.agreement_place is not None:
        ahead = analysis.ahead
        contest_block = [
            "",
            "👥 <b>Кто впереди</b>",
            f"всего  ·  {ahead.total}",
            (
                f"{'с договором' if paid else 'с согласием'}  ·  {ahead.with_agreement}"
                f"  →  вы <b>{analysis.agreement_place}</b>-й среди них"
            ),
        ]
        if not paid:
            contest_block.append(
                f"с ВПП  ·  {analysis.hpp_ahead}"
                f"  →  реальное <b>{analysis.hpp_place}</b>-е из {places}"
            )
        contest_block += [
            "",
            "📌 <b>На программе сейчас</b>",
        ]
        if paid:
            contest_block.append(
                f"с договором  ·  <b>{ahead.with_agreement + int(me.has_contract)}</b> из {places}"
            )
        else:
            contest_block.append(
                f"с ВПП, займут место  ·  <b>{analysis.hpp_total}</b> из {places}"
            )
        if analysis.mtp_without_consent and not paid:
            contest_block.append(
                f"ОВП без согласия  ·  {analysis.mtp_without_consent}  — их места могут освободиться"
            )

    if paid:
        footer = [
            "",
            "<i>На платное зачисляют по договору и оплате, не по согласию.</i>",
            "<i>Места смотрите относительно числа платных мест на программе.</i>",
        ]
    else:
        footer = [
            "",
            "<i>ОВП — основной высший приоритет: сюда проходите, даже если согласия ещё нет.</i>",
            "<i>ВПП — высший проходной приоритет: по нему зачисляют, нужно согласие.</i>",
            "<i>Согласие одно на весь ИТМО. Основной этап — до 24.08, 12:00 МСК.</i>",
        ]
    return "\n".join(header + places_block + you_block + contest_block + footer)


def format_list(analysis: Analysis, code: str, *, first_priority: bool) -> str:
    rating = analysis.rating
    me = analysis.me
    paid = rating.is_paid
    title = "Среди 1 приоритета" if first_priority else "Общий список"
    lines = [
        f"🎓 <b>{_esc(rating.title)}</b>",
        f"📋 {title}  ·  {FINANCING_LABELS.get(rating.financing, rating.financing)}"
        f"  ·  код <code>{_esc(code)}</code>",
        "",
    ]

    if me is None:
        lines.append("❌ Код не найден в этом списке.")
        return "\n".join(lines)

    if first_priority:
        if me.priority != 1:
            prio = me.priority if me.priority is not None else "—"
            lines += [
                f"Эта программа у вас не первый приоритет (сейчас {prio}).",
                f"Ниже — текущая голова списка 1 приоритета ({len(analysis.prio1)} чел.).",
                "",
            ]
        elif analysis.prio1_position is not None:
            lines.append(
                f"Ваше место среди 1 приоритета: <b>{analysis.prio1_position}</b> "
                f"из {len(analysis.prio1)}  (в общем списке #{me.position})"
            )
            lines.append("")
        index_by_id = {person.sspvo_id: i + 1 for i, person in enumerate(analysis.prio1)}
        for person in analysis.neighbors_prio1:
            p1 = index_by_id.get(person.sspvo_id, "—")
            highlight = person.sspvo_id == me.sspvo_id
            mark = "➤" if highlight else " "
            you = "  ← вы" if highlight else ""
            extra = (
                (
                    "  оплачен"
                    if person.has_paid_contract
                    else "  дог."
                    if person.has_approved_contract
                    else ""
                )
                if paid
                else ("  согл." if person.is_send_agreement else "")
            )
            lines.append(
                f"{mark} {_status_emoji(person, paid=paid)} <b>#{p1}</b> (общ. {person.position})  "
                f"№{_esc(person.sspvo_id)}  ВИ+ИД {_fmt_score(person.total_scores, 1)}"
                f"  дип.{_fmt_diploma(person.diploma_average)}{extra}{you}"
            )
    else:
        lines.append(f"📍 Ваше место: <b>#{me.position}</b> из {analysis.overall_total}")
        lines.append("")
        for person in analysis.neighbors:
            lines.append(
                _person_line(person, highlight=person.sspvo_id == me.sspvo_id, paid=paid)
            )

    legend = (
        "пр. — приоритет, дог. — договор, оплачен — договор оплачен"
        if paid
        else "пр. — приоритет, согл. — согласие на зачисление"
    )
    lines += [
        "",
        (
            "🟢 договор оплачен  ·  🟡 договор без оплаты  ·  ⚪ без договора"
            if paid
            else "🟢 сюда, согласие есть  ·  🟡 сюда, согласия нет  ·  🔘 другая программа  ·  ⚪ нет пометки"
        ),
        legend,
    ]
    return "\n".join(lines)


def format_help() -> str:
    return "\n".join(
        [
            "👋 <b>Как пользоваться</b>",
            "Сохраните код поступающего, выберите программу, смотрите сводку и себя в списках.",
            "",
            "<b>Как ранжируют</b> (правила ИТМО, п. 51)",
            "ВИ+ИД → балл ВИ → тип испытания (ЯП / мегаконкурс / портфолио / ВЭ) → ИД → средний балл диплома.",
            "В конкурсный список попадают с ВИ ≥ 50.",
            "",
            "<b>ОВП</b> — основной высший приоритет: самая высокая программа, куда вы сейчас проходите, даже без согласия.",
            "<b>ВПП</b> — высший проходной приоритет: то же, но только при согласии. По ВПП зачисляют.",
            "Согласие одно на весь ИТМО. Основной этап: до 24.08 12:00 МСК, приказы 25.08.",
            "",
            "На <b>платное</b> зачисляют по договору и оплате, не по согласию.",
            "",
            "Команды: /start · /code · /programs · /help",
        ]
    )
