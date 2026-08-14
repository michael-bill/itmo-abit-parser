from __future__ import annotations

import html
from datetime import datetime

from .models import Analysis, Applicant

STATUS_LABELS = {
    "recommended": "предварительно рекомендован на эту программу",
    "pass_another": "предварительно рекомендован на другую программу",
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def _yes_no(flag: bool) -> str:
    return "да" if flag else "нет"


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


def _status_emoji(person: Applicant) -> str:
    if person.status == "recommended":
        return "🟢"
    if person.status == "pass_another":
        return "🟡"
    return "⚪"


def _person_line(person: Applicant, *, highlight: bool = False) -> str:
    mark = "➤ " if highlight else "    "
    you = "  ← вы" if highlight else ""
    diploma = _fmt_diploma(person.diploma_average)
    agr = "согл." if person.is_send_agreement else "без согл."
    prio = person.priority if person.priority is not None else "—"
    return (
        f"{mark}{_status_emoji(person)} <b>#{person.position}</b>  №{_esc(person.sspvo_id)}"
        f"  пр.{_esc(prio)}  ВИ+ИД {_fmt_score(person.total_scores, 1)}"
        f"  дип.{diploma}  {agr}{you}"
    )


def format_summary(analysis: Analysis, code: str, program_name: str) -> str:
    rating = analysis.rating
    places = rating.budget_places
    target = rating.target_places
    lines = [
        f"🎓 <b>{_esc(rating.title or program_name)}</b>",
        f"Мест: <b>{places}</b>" + (f"  (ЦК: {target})" if target else "  (ЦК: 0)"),
        f"Обновлено: {_esc(_fmt_time(rating.update_time))}",
        f'<a href="{_esc(rating.source_url)}">Открыть список на сайте ИТМО</a>',
        "",
        f"👤 Код: <code>{_esc(code)}</code>",
    ]

    me = analysis.me
    if me is None:
        lines += [
            "",
            "❌ Код не найден в этом конкурсном списке.",
            "Проверьте код или выберите другую программу.",
        ]
        return "\n".join(lines)

    lines += [
        "",
        f"📋 Место в общем списке: <b>{me.position}</b> из {analysis.overall_total}",
    ]
    if me.priority == 1 and analysis.prio1_position is not None:
        lines.append(
            f"⭐ Среди 1 приоритета: <b>{analysis.prio1_position}</b> из {len(analysis.prio1)}"
        )
    else:
        prio = me.priority if me.priority is not None else "—"
        lines.append(
            f"⭐ 1 приоритет: эта программа у вас {prio}-я "
            f"(в 1 приоритете здесь {len(analysis.prio1)} чел.)"
        )

    lines += [
        "",
        f"Конкурс: {_esc(_quota_label(me))}",
        f"Приоритет: <b>{_esc(me.priority if me.priority is not None else '—')}</b>",
        f"Вид испытания: {_esc(me.exam_label)}",
        (
            f"Баллы: ВИ {_fmt_score(me.exam_scores, 1)} + ИД {_fmt_score(me.ia_scores, 1)}"
            f" = <b>{_fmt_score(me.total_scores, 1)}</b>"
        ),
        f"Средний балл диплома: <b>{_fmt_diploma(me.diploma_average)}</b>",
        f"Согласие на зачисление: {_yes_no(me.is_send_agreement)}",
        f"Основной высший приоритет: {_yes_no(me.main_top_priority)}",
        f"Высший проходной приоритет: {_yes_no(me.highest_passageway_priority)}",
    ]

    if me.status:
        lines.append(f"Пометка сайта: {_esc(STATUS_LABELS.get(me.status, me.status))}")
    else:
        lines.append("Пометка сайта: нет (не в зоне рекомендации)")

    if not me.has_exam_score:
        lines += [
            "",
            "⚠️ Баллы ВИ пока 0. В списке вы стоите среди тех, у кого тоже нет баллов, "
            "и ранжируетесь по среднему баллу диплома. После публикации результатов "
            "место может сильно измениться.",
        ]

    if analysis.ahead:
        ahead = analysis.ahead
        lines += [
            "",
            "<b>Кто впереди в общем списке</b>",
            f"• всего: {ahead.total}",
            f"• с ненулевыми баллами ВИ+ИД: {ahead.with_scores}",
            f"• с 1 приоритетом: {ahead.first_priority}",
            f"• с согласием: {ahead.with_agreement}",
            f"• рекомендованы сюда: {ahead.recommended}",
        ]

    prio1_scored = sum(1 for person in analysis.prio1 if person.has_exam_score)
    lines += [
        "",
        "<b>Конкурс среди 1 приоритета</b>",
        f"• заявлений с 1 приоритетом: {len(analysis.prio1)}",
        f"• из них с баллами ВИ+ИД: {prio1_scored}",
        f"• бюджетных мест: {places}",
    ]
    if analysis.ahead_prio1 is not None:
        lines.append(
            f"• впереди вас среди 1 приоритета: {analysis.ahead_prio1.total}"
            f" (с баллами: {analysis.ahead_prio1.with_scores})"
        )
    if prio1_scored < places:
        lines.append(
            f"• сейчас людей с 1 приоритетом и баллами меньше числа мест "
            f"({prio1_scored} &lt; {places}) — много заявлений ещё без ВИ."
        )
    elif analysis.prio1:
        cutoff_idx = min(places, len(analysis.prio1)) - 1
        cutoff = analysis.prio1[cutoff_idx]
        lines.append(
            f"• {places}-й в списке 1 приоритета: место #{cutoff.position}, "
            f"ВИ+ИД {_fmt_score(cutoff.total_scores, 1)}, дип.{_fmt_diploma(cutoff.diploma_average)}"
        )

    rec = analysis.recommended
    lines += [
        "",
        "<b>Как это видит сайт</b>",
        f"• предварительно рекомендованы сюда: {len(rec)} (обычно = числу мест)",
        f"• высший проходной приоритет: "
        f"{sum(1 for person in rating.all_applicants if person.highest_passageway_priority)}",
    ]
    if rec:
        last = rec[-1]
        lines.append(
            f"• последний из рекомендованных: место #{last.position}, "
            f"ВИ+ИД {_fmt_score(last.total_scores, 1)}, дип.{_fmt_diploma(last.diploma_average)}"
        )
    lines.append(
        "\n<i>Рекомендация и «проходной приоритет» — пометки суперсервиса, "
        "а не наш пересчёт. Итог зависит от согласий и других программ.</i>"
    )
    return "\n".join(lines)


def format_list(analysis: Analysis, code: str, *, first_priority: bool) -> str:
    rating = analysis.rating
    me = analysis.me
    title = "Среди 1 приоритета" if first_priority else "Общий список"
    lines = [
        f"🎓 <b>{_esc(rating.title)}</b>",
        f"<b>{title}</b> · код <code>{_esc(code)}</code>",
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
            lines.append(
                f"{mark} {_status_emoji(person)} <b>#{p1}</b> (общ. {person.position})  "
                f"№{_esc(person.sspvo_id)}  ВИ+ИД {_fmt_score(person.total_scores, 1)}"
                f"  дип.{_fmt_diploma(person.diploma_average)}"
                f"{'  согл.' if person.is_send_agreement else ''}{you}"
            )
    else:
        lines.append(f"Ваше место: <b>#{me.position}</b> из {analysis.overall_total}")
        lines.append("")
        for person in analysis.neighbors:
            lines.append(_person_line(person, highlight=person.sspvo_id == me.sspvo_id))

    lines += [
        "",
        "🟢 рекомендован сюда  ·  🟡 рекомендован на другую  ·  ⚪ нет пометки",
        "пр. — приоритет, согл. — согласие на зачисление",
    ]
    return "\n".join(lines)


def format_help() -> str:
    return "\n".join(
        [
            "<b>Как пользоваться</b>",
            "1. Сохраните уникальный код поступающего (Госуслуги / суперсервис).",
            "2. Выберите программу — бот подтянет официальный список ИТМО.",
            "3. Смотрите сводку, себя в общем списке и среди тех, у кого эта программа — 1 приоритет.",
            "",
            "<b>Что значит сводка</b>",
            "• <b>ВИ</b> — вступительное испытание, <b>ИД</b> — индивидуальные достижения.",
            "• Список отсортирован по ВИ+ИД, при равенстве — по среднему баллу диплома.",
            "• <b>1 приоритет</b> — отфильтрованный тот же список, только priority = 1.",
            "• <b>Основной высший приоритет</b> — для поступающего это сейчас главная программа.",
            "• <b>Высший проходной приоритет</b> — он проходит именно сюда с учётом других заявлений.",
            "• <b>Рекомендован</b> — пометка сайта, обычно совпадает с числом бюджетных мест.",
            "",
            "Команды: /start · /code · /programs · /help",
        ]
    )
