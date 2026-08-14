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


def _ahead(people: tuple[Applicant, ...], me: Applicant) -> AheadStats:
    before = [person for person in people if person.position < me.position]
    return AheadStats(
        total=len(before),
        with_scores=sum(1 for person in before if person.has_exam_score),
        with_agreement=sum(1 for person in before if person.is_send_agreement),
        first_priority=sum(1 for person in before if person.priority == 1),
        recommended=sum(1 for person in before if person.status == "recommended"),
    )


def _slice_around(people: tuple[Applicant, ...], index: int, window: int = NEIGHBOR_WINDOW) -> tuple[Applicant, ...]:
    start = max(0, index - window)
    end = min(len(people), index + window + 1)
    return people[start:end]


def analyze(rating: ProgramRating, code: str) -> Analysis:
    everyone = rating.all_applicants
    me = _find(everyone, code)
    prio1 = _prio1(rating.general)
    recommended = tuple(person for person in everyone if person.status == "recommended")

    overall_position = me.position if me else None
    prio1_position = None
    neighbors: tuple[Applicant, ...] = ()
    neighbors_prio1: tuple[Applicant, ...] = ()
    ahead = None
    ahead_prio1 = None

    if me is not None:
        ahead = _ahead(everyone, me)
        idx = next((i for i, person in enumerate(everyone) if person.sspvo_id == me.sspvo_id), None)
        if idx is not None:
            neighbors = _slice_around(everyone, idx)
        if me.priority == 1:
            p1_idx = next((i for i, person in enumerate(prio1) if person.sspvo_id == me.sspvo_id), None)
            if p1_idx is not None:
                prio1_position = p1_idx + 1
                neighbors_prio1 = _slice_around(prio1, p1_idx)
                ahead_prio1 = AheadStats(
                    total=p1_idx,
                    with_scores=sum(1 for person in prio1[:p1_idx] if person.has_exam_score),
                    with_agreement=sum(1 for person in prio1[:p1_idx] if person.is_send_agreement),
                    first_priority=p1_idx,
                    recommended=sum(1 for person in prio1[:p1_idx] if person.status == "recommended"),
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
    )
