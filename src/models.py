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
    has_approved_contract: bool
    has_paid_contract: bool
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

    @property
    def has_contract(self) -> bool:
        return self.has_approved_contract or self.has_paid_contract

    def has_commitment(self, paid: bool) -> bool:
        return self.has_contract if paid else self.is_send_agreement


@dataclass(frozen=True)
class ProgramRating:
    title: str
    competitive_group_id: int
    financing: str
    budget_places: int
    contract_places: int
    target_places: int
    update_time: datetime | None
    fetched_at: datetime | None
    general: tuple[Applicant, ...]
    target_quota: tuple[Applicant, ...]
    source_url: str

    @property
    def is_paid(self) -> bool:
        return self.financing != "budget"

    @property
    def places(self) -> int:
        return self.contract_places if self.is_paid else self.budget_places

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
    with_hpp: int
    with_mtp: int


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
    agreement_place: int | None
    hpp_place: int | None
    hpp_ahead: int
    hpp_total: int
    mtp_total: int
    mtp_without_consent: int
    recommended_total: int
    recommended_position: int | None
    recommended_neighbors: tuple[Applicant, ...]
