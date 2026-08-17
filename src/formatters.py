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


def _ranking_url(source_url: str) -> str:
    return source_url.replace("/rating/", "/ranking/", 1)


def _recommended_line(
    person: Applicant,
    *,
    index: int,
    highlight: bool = False,
) -> str:
    mark = "➤" if highlight else " "
    you = "  ← вы" if highlight else ""
    agr = "согл." if person.is_send_agreement else "без согл."
    return (
        f"{mark} {_status_emoji(person)} <b>#{index}</b> (общ. {person.position})  "
        f"№{_esc(person.sspvo_id)}  ВИ+ИД {_fmt_score(person.total_scores, 1)}"
        f"  дип.{_fmt_diploma(person.diploma_average)}  {agr}{you}"
    )


def _format_recommended_block(analysis: Analysis) -> list[str]:
    if (
        analysis.rating.is_paid
        or not analysis.recommended_neighbors
        or analysis.recommended_position is None
    ):
        return []

    me = analysis.me
    total = analysis.recommended_total
    lines = [
        "",
        "🎨 <b>Предварительно рекомендованные</b>",
        f"ваше место на сайте  ·  <b>{analysis.recommended_position}</b> из {total}",
    ]
    if (
        analysis.hpp_place is not None
        and analysis.recommended_position != analysis.hpp_place
    ):
        lines.append(
            "<i>это подсветка ИТМО, не очередь зачисления. "
            "Жёлтые без согласия место не занимают.</i>"
        )
    lines.append("")
    index_by_id = {
        person.sspvo_id: i + 1 for i, person in enumerate(analysis.recommended)
    }
    for person in analysis.recommended_neighbors:
        rec_no = index_by_id.get(person.sspvo_id, "—")
        highlight = me is not None and person.sspvo_id == me.sspvo_id
        lines.append(_recommended_line(person, index=rec_no, highlight=highlight))
    lines.append("🟢 согласие есть  ·  🟡 согласия нет")
    return lines


def _verdict(analysis: Analysis) -> str:
    me = analysis.me
    rating = analysis.rating
    places = rating.places
    assert me is not None
    hpp_place = analysis.hpp_place or 0
    status = me.status

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

    if me.highest_passageway_priority:
        if hpp_place <= places:
            if me.is_send_agreement:
                return (
                    f"Вас зачислят на эту программу.\n"
                    f"Реальное место по ВПП: {hpp_place}-е из {places} бюджетных."
                )
            return (
                "ИТМО ставит вас в проходные по ВПП, но согласия пока нет.\n"
                "Без согласия сюда не зачислят."
            )
        return (
            f"Согласие есть, но по ВПП вы за чертой: {hpp_place}-е место "
            f"при {places} бюджетных."
        )

    if me.main_top_priority:
        if not me.is_send_agreement:
            return (
                "По ОВП сюда проходите — это ваш лучший вариант по баллам.\n"
                "Согласия ещё нет: без него место не закрепят."
            )
        return (
            "По ОВП сюда проходите, согласие есть.\n"
            "Зачисление оформят по ВПП после пересчёта списка."
        )

    if status in ("pass_another", "in_another_order"):
        return (
            "ИТМО ведёт вас на другую программу с более высоким приоритетом.\n"
            "На эту сейчас не зачислят."
        )

    if status in ("recommended", "in_order") and me.is_send_agreement:
        return (
            "ИТМО рекомендует вас сюда, согласие есть.\n"
            "Если в списке ещё нет ВПП — ориентируйтесь на статус recommended."
        )

    if status == "recommended":
        return (
            "ИТМО считает, что вы сюда проходите, но согласия нет.\n"
            "Без согласия к сроку место не закрепят."
        )

    if status == "in_order":
        return "Вы в приказе на зачисление на эту программу."

    if me.is_send_agreement and hpp_place <= places:
        return (
            f"Согласие есть, впереди с ВПП {analysis.hpp_ahead} чел. — это меньше {places} мест.\n"
            "Но у вас нет ВПП на эту программу: ИТМО пока не ведёт зачисление сюда."
        )

    if me.priority and me.priority > 1:
        return (
            f"Эта программа у вас {me.priority}-й приоритет, ОВП/ВПП здесь нет.\n"
            "Сюда могут зачислить только если не пройдёте на программы выше."
        )

    return (
        "Сюда сейчас не проходите по пометкам ИТМО.\n"
        "Нет ОВП, ВПП и рекомендации на эту программу."
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
        "Сайты ИТМО: "
        f'<a href="{_esc(rating.source_url)}">конкурсный список</a>'
        f'  ·  <a href="{_esc(_ranking_url(rating.source_url))}">предварительно рекомендованные</a>',
        "",
        f"🔢 код  <code>{_esc(code)}</code>",
    ]

    if me is None:
        return "\n".join(header + ["", "❌ Этот код в списке не найден."])

    prio = me.priority if me.priority is not None else "—"
    places_block = ["", "📊 <b>Места</b>"]
    if not paid and analysis.hpp_place is not None:
        if me.highest_passageway_priority:
            places_block.append(
                f"по ВПП  ·  <b>{analysis.hpp_place}</b> из {places}"
            )
        else:
            places_block.append(
                f"очередь с ВПП впереди  ·  <b>{analysis.hpp_place}</b> из {places}"
            )
    elif paid and analysis.agreement_place is not None:
        places_block.append(
            f"среди договоров  ·  <b>{analysis.agreement_place}</b>"
        )
    places_block.append(
        f"в общем списке  ·  <b>{me.position}</b> из {analysis.overall_total}"
    )
    if me.priority == 1 and analysis.prio1_position is not None:
        places_block.append(
            f"среди 1 приоритета  ·  <b>{analysis.prio1_position}</b> из {len(analysis.prio1)}"
        )
    else:
        places_block.append(
            f"ваш приоритет  ·  <b>{_esc(prio)}</b>    среди 1 приоритета здесь {len(analysis.prio1)}"
        )
    if not paid:
        places_block.append("<i>на зачисление влияет только место по ВПП</i>")

    verdict_block = [
        "",
        f"<blockquote>{_esc(_verdict(analysis))}</blockquote>",
    ]

    you_block = [
        "",
        "👤 <b>Вы</b>",
        (
            f"баллы  ·  ВИ {_fmt_score(me.exam_scores, 1)} + ИД {_fmt_score(me.ia_scores, 1)}"
            f" = <b>{_fmt_score(me.total_scores, 1)}</b>"
        ),
        f"диплом  ·  {_fmt_diploma(me.diploma_average)}",
        f"испытание  ·  {_esc(me.exam_label)}",
    ]
    if me.quota == "target":
        you_block.append(f"конкурс  ·  {_esc(_quota_label(me))}")
    you_block += [
        (
            f"договор  ·  {_flag(me.has_approved_contract)}"
            f"    оплата  ·  {_flag(me.has_paid_contract)}"
            if paid
            else f"согласие  ·  {_flag(me.is_send_agreement)}"
        ),
        f"пометка ИТМО  ·  {_color_label(me, paid=paid)}",
    ]
    if not paid:
        you_block.append(
            f"ОВП  ·  {_flag(me.main_top_priority)}"
            f"    ВПП  ·  {_flag(me.highest_passageway_priority)}"
        )

    contest_block: list[str] = []
    if paid and analysis.ahead and analysis.agreement_place is not None:
        contest_block = [
            "",
            "👥 <b>Кто впереди</b>",
            f"всего  ·  {analysis.ahead.total}",
            (
                f"с договором  ·  {analysis.ahead.with_agreement}"
                f"  →  вы <b>{analysis.agreement_place}</b>-й среди них"
            ),
            "",
            "📌 <b>На программе сейчас</b>",
            (
                f"с договором  ·  <b>{analysis.ahead.with_agreement + int(me.has_contract)}</b>"
                f" из {places}"
            ),
        ]
    elif not paid:
        contest_block = [
            "",
            "📌 <b>На программе сейчас</b>",
            f"с ВПП, займут место  ·  <b>{analysis.hpp_total}</b> из {places}",
        ]
        if analysis.mtp_without_consent:
            contest_block.append(
                f"ОВП без согласия  ·  {analysis.mtp_without_consent}"
                "  — без согласия место не занимают"
            )

    if paid:
        footer = [
            "",
            "💡 <b>Пояснения</b>",
            "<i>На платное зачисляют по договору и оплате, не по согласию.</i>",
            "<i>Места смотрите относительно числа платных мест на программе.</i>",
            "",
            "<i>Остались вопросы — нажмите ❓ FAQ внизу.</i>",
        ]
    else:
        footer = [
            "",
            "💡 <b>Пояснения</b>",
            "<i>ОВП — ИТМО считает, что вы сюда проходите по баллам, даже без согласия.</i>",
            "<i>ВПП — то же самое, но с согласием; по ВПП и зачисляют.</i>",
            "<i>Согласие одно на вуз и сразу на все программы. Основной этап — до 24.08, 12:00 МСК.</i>",
            "",
            "<i>Остались вопросы — нажмите ❓ FAQ внизу.</i>",
        ]
    return "\n".join(
        header
        + verdict_block
        + you_block
        + places_block
        + contest_block
        + _format_recommended_block(analysis)
        + footer
    )


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


RULES_URL = "https://abit.itmo.ru/page/79"


def format_help() -> str:
    return format_faq()


def format_faq(topic: str | None = None) -> str:
    if topic == "bot":
        return "\n".join(
            [
                "🤖 <b>Как пользоваться ботом</b>",
                "",
                "1. Пришлите уникальный код с Госуслуг — бот его запомнит.",
                "2. Выберите программу из избранного или нажмите «Все программы» и найдите по названию / коду 09.04.04.",
                "3. Смотрите сводку: место, согласие, проходите ли вы сюда.",
                "4. «Я в общем списке» — соседи вокруг вас.",
                "5. «Обновить» заново тянет список с сайта ИТМО.",
                "",
                "Код можно сменить кнопкой «Мой код» или командой /code.",
                "Списки в боте те же, что на abit.itmo.ru. Сам ИТМО обновляет их примерно раз в час — смотрите строку «список ИТМО от …».",
                "",
                "Команды: /start · /code · /programs · /faq",
            ]
        )
    if topic == "summary":
        return "\n".join(
            [
                "📊 <b>Что значит сводка</b>",
                "",
                "<b>Цитата сразу после шапки</b> — вывод: проходите ли вы сюда сейчас. На бюджете главное число там же: место по ВПП.",
                "",
                "<b>Место в общем списке</b> — позиция среди всех подавших. Это ещё не место на зачисление.",
                "",
                "<b>Среди 1 приоритета</b> — только те, у кого эта программа стоит первой. На зачисление это не влияет.",
                "",
                "<b>Очередь с ВПП</b> — если ВПП у вас нет, это сколько людей с ВПП уже впереди, а не ваше место зачисления.",
                "",
                "<b>Предварительно рекомендованные</b> — как ИТМО подсвечивает людей на сайте. Жёлтые без согласия место не занимают. Зачисляют по ВПП, не по этому списку.",
                "",
                "<b>С согласием / без согласия</b> — согласие одно на весь университет, не на программу. Без него ИТМО не зачислит, даже если вы «проходите» по баллам.",
                "",
                "Не смотрите только на общее место. Человек ниже в списке с ВПП может занять место, а человек выше без согласия — нет.",
            ]
        )
    if topic == "budget":
        return "\n".join(
            [
                "🏛 <b>Как зачисляют на бюджет</b>",
                "",
                "Правила ИТМО, п. 56–57. Зачисляют не «кто выше в списке», а по высшему проходному приоритету.",
                "",
                "<b>ОВП</b> — основной высший приоритет. Самая высокая программа, куда вы сейчас проходите по баллам. Считается даже без согласия. На сайте вы там жёлтый или зелёный.",
                "",
                "<b>ВПП</b> — высший проходной приоритет. То же самое, но только если согласие уже есть. <b>По ВПП и зачисляют.</b>",
                "",
                "Согласие одно на весь ИТМО: подали — оно действует на все ваши бюджетные программы. Зачислят на самую высокую, куда проходите.",
                "",
                "Без согласия место не закрепят, даже если вы зелёный/жёлтый и «проходите». Если согласия нет к сроку — место уйдёт тому, у кого согласие есть.",
                "",
                "Жёлтые в этом списке место не занимают, пока не подадут согласие. Серые проходят на другую программу и это место не займут.",
            ]
        )
    if topic == "paid":
        return "\n".join(
            [
                "💳 <b>Платное</b>",
                "",
                "На платное согласие не нужно. Зачисляют, если вы проходите в пределах платных мест, есть договор и университет видит оплату (обычно первый платёж). Правила, п. 55 и 58.",
                "",
                "Бюджет и платное — разные списки и разные приоритеты. Можно параллельно идти и туда, и туда.",
                "",
                "В сводке на платном смотрите договор и оплату, а не ОВП/ВПП.",
            ]
        )
    if topic == "colors":
        return "\n".join(
            [
                "🎨 <b>Цвета на сайте и в боте</b>",
                "",
                "Это пометки ИТМО «кто сейчас проходит», не отдельный рейтинг.",
                "",
                "🟢 рекомендован сюда, согласие есть — почти наверняка зачислят, если ничего не отзовут.",
                "🟡 рекомендован сюда, согласия нет — проходите, но место ещё не ваше.",
                "🔘 рекомендован на другую программу — сюда его не зачислят.",
                "⚪ без пометки — сюда сейчас не проходит.",
                "",
                "На платном: зелёный — договор оплачен, жёлтый — договор без оплаты.",
                "",
                "Цвета ≈ симулятор. Очередь на зачисление — место по ВПП в цитате вверху сводки.",
            ]
        )
    if topic == "rank":
        return "\n".join(
            [
                "🔢 <b>Как ранжируют список</b>",
                "",
                "Правила, п. 51. Сравнивают по очереди:",
                "1. сумма ВИ + ИД",
                "2. балл ВИ",
                "3. тип испытания: ЯП / мегаконкурс / портфолио / ВЭ",
                "4. баллы ИД",
                "5. средний балл диплома",
                "",
                "В конкурсный список попадают с ВИ не меньше 50. Пока балла нет — вы в списке подавших, не в конкурсе.",
            ]
        )
    if topic == "dates":
        return "\n".join(
            [
                "📅 <b>Сроки магистратуры 2026</b>",
                "",
                "Правила, п. 81–82.",
                "",
                "<b>Бюджет</b>",
                "• документы принимали до 20 августа",
                "• основной этап: согласие до <b>24 августа, 12:00 МСК</b>, приказы 25 августа",
                "• доп. этап: согласие до <b>26 августа, 12:00 МСК</b>, приказы 27 августа",
                "",
                "<b>Платное</b>",
                "• документы до 28 августа",
                "• зачисление до 30 августа",
                "",
                "Согласие можно отозвать и подать заново, на Госуслугах — не чаще раза в 2 часа. В день приказов списки уже не правят.",
            ]
        )
    return "\n".join(
        [
            "❓ <b>FAQ</b>",
            "Коротко про сводку и зачисление в магистратуру ИТМО. Выберите тему.",
            "",
            "Это не официальный ответ приёмной комиссии. Полные правила:",
            f'<a href="{RULES_URL}">abit.itmo.ru/page/79</a>',
        ]
    )
