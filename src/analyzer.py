from __future__ import annotations

from .models import AheadStats, Analysis, Applicant, ProgramRating

NEIGHBOR_WINDOW = 5


def _find(applicants: tuple[Applicant, ...], code: str) -> Applicant | None:
    needle = code.strip()
    for person in applicants:
        if person.sspvo_id == needle:
            return person
    return None


def _prio1(applicants: tuple[Applicant, ...]) -> tuple[Applicant, ...]:
    return tuple(person for person in applicants if person.priority == 1)


def _ahead(people: tuple[Applicant, ...], me: Applicant, *, paid: bool) -> AheadStats:
    before = [person for person in people if person.position < me.position]
    return AheadStats(
        total=len(before),
        with_scores=sum(1 for person in before if person.has_exam_score),
        with_agreement=sum(1 for person in before if person.has_commitment(paid)),
        first_priority=sum(1 for person in before if person.priority == 1),
        recommended=sum(1 for person in before if person.status == "recommended"),
        with_hpp=sum(1 for person in before if person.highest_passageway_priority),
        with_mtp=sum(1 for person in before if person.main_top_priority),
    )


def _slice_around(people: tuple[Applicant, ...], index: int, window: int = NEIGHBOR_WINDOW) -> tuple[Applicant, ...]:
    start = max(0, index - window)
    end = min(len(people), index + window + 1)
    return people[start:end]


def analyze(rating: ProgramRating, code: str) -> Analysis:
    everyone = rating.all_applicants
    me = _find(everyone, code)
    prio1 = _prio1(rating.general)
    paid = rating.is_paid
    recommended = tuple(person for person in everyone if person.status == "recommended")
    hpp_total = sum(1 for person in everyone if person.highest_passageway_priority)
    mtp_people = [person for person in everyone if person.main_top_priority]
    mtp_total = len(mtp_people)
    mtp_without_consent = sum(1 for person in mtp_people if not person.has_commitment(paid))

    overall_position = me.position if me else None
    prio1_position = None
    neighbors: tuple[Applicant, ...] = ()
    neighbors_prio1: tuple[Applicant, ...] = ()
    ahead = None
    ahead_prio1 = None
    agreement_place = None
    hpp_place = None
    hpp_ahead = 0

    if me is not None:
        ahead = _ahead(everyone, me, paid=paid)
        hpp_ahead = ahead.with_hpp
        agreement_place = ahead.with_agreement + 1
        hpp_place = ahead.with_hpp + 1
        idx = next((i for i, person in enumerate(everyone) if person.sspvo_id == me.sspvo_id), None)
        if idx is not None:
            neighbors = _slice_around(everyone, idx)
        if me.priority == 1:
            p1_idx = next((i for i, person in enumerate(prio1) if person.sspvo_id == me.sspvo_id), None)
            if p1_idx is not None:
                prio1_position = p1_idx + 1
                neighbors_prio1 = _slice_around(prio1, p1_idx)
                p1_before = prio1[:p1_idx]
                ahead_prio1 = AheadStats(
                    total=p1_idx,
                    with_scores=sum(1 for person in p1_before if person.has_exam_score),
                    with_agreement=sum(1 for person in p1_before if person.has_commitment(paid)),
                    first_priority=p1_idx,
                    recommended=sum(1 for person in p1_before if person.status == "recommended"),
                    with_hpp=sum(1 for person in p1_before if person.highest_passageway_priority),
                    with_mtp=sum(1 for person in p1_before if person.main_top_priority),
                )
        else:
            neighbors_prio1 = prio1[: NEIGHBOR_WINDOW * 2 + 1]

    return Analysis(
        rating=rating,
        me=me,
        overall_total=len(everyone),
        overall_position=overall_position,
        prio1=prio1,
        prio1_position=prio1_position,
        ahead=ahead,
        ahead_prio1=ahead_prio1,
        recommended=recommended,
        neighbors=neighbors,
        neighbors_prio1=neighbors_prio1,
        agreement_place=agreement_place,
        hpp_place=hpp_place,
        hpp_ahead=hpp_ahead,
        hpp_total=hpp_total,
        mtp_total=mtp_total,
        mtp_without_consent=mtp_without_consent,
    )
