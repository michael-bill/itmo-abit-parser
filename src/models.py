from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Applicant:
    sspvo_id: str
    position: int
    priority: int | None
    contest: str | None
    exam_type: str | None
    ia_scores: float
    exam_scores: float
    total_scores: float
    diploma_average: float | None
    is_send_agreement: bool
    status: str | None
    main_top_priority: bool
    highest_passageway_priority: bool
    quota: str  # general | target

    @property
    def exam_label(self) -> str:
        return (self.contest or self.exam_type or "—").strip() or "—"

    @property
    def has_exam_score(self) -> bool:
        return self.total_scores > 0 or self.exam_scores > 0


@dataclass(frozen=True)
class ProgramRating:
    title: str
    competitive_group_id: int
    budget_places: int
    target_places: int
    update_time: datetime | None
    general: tuple[Applicant, ...]
    target_quota: tuple[Applicant, ...]
    source_url: str

    @property
    def all_applicants(self) -> tuple[Applicant, ...]:
        return self.target_quota + self.general


@dataclass(frozen=True)
class AheadStats:
    total: int
    with_scores: int
    with_agreement: int
    first_priority: int
    recommended: int


@dataclass(frozen=True)
class Analysis:
    rating: ProgramRating
    me: Applicant | None
    overall_total: int
    overall_position: int | None
    prio1: tuple[Applicant, ...]
    prio1_position: int | None
    ahead: AheadStats | None
    ahead_prio1: AheadStats | None
    recommended: tuple[Applicant, ...]
    neighbors: tuple[Applicant, ...]
    neighbors_prio1: tuple[Applicant, ...]
