"""The generated-paper intake contract (spec 3C, 8.8; Pass 2 Stage D, D31).

One body for every source: the paper's own fields, exactly as a hand-made paper has them,
plus a ``generated`` block with the source, the module, its run, when it generated the paper,
its ``inputs`` and ``citations``, and one source block carrying what the specification names
for that source and nothing else:

    materiality         "the benchmark, the band and the figures from the spine"
    sampling            "the formula and the seed"
    analytical_review   "current year against prior, with the thresholds used"
    workmind            "the run id, the inputs and the source-row citations"
    spine               lead schedules and the adjustment chain: Stage E

``inputs`` and ``citations`` are kept verbatim: their shape belongs to modules that do not
exist yet, so nothing is assumed beyond "present and not empty". The source blocks are strict:
an unknown key is refused, so a module cannot smuggle a field the contract does not name.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from oak_binder.models import WpGeneration

Source = Literal["materiality", "sampling", "analytical_review", "workmind", "spine"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def filled(value: Any, name: str) -> Any:
    """Present and not empty: not None, not blank text, not an empty list or object."""
    if value is None:
        raise ValueError(f"{name} must be present")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} must not be blank")
    if isinstance(value, list | dict) and len(value) == 0:
        raise ValueError(f"{name} must not be empty")
    return value


class PaperFields(Strict):
    """The paper as spec 3B defines it; the same fields a person would type."""

    ref: str
    section: str
    title: str
    sa_refs: list[str] = []
    objective: str | None = None
    procedure: str | None = None
    population_sample: str | None = None
    result: str | None = None
    conclusion: str | None = None


class SpineFigures(Strict):
    """The figures the memo took from the Financial Spine, and the version they came from
    (checked against the binder's linked version, decision 5)."""

    version_id: uuid.UUID
    figures: Any

    @field_validator("figures")
    @classmethod
    def _figures(cls, value: Any) -> Any:
        return filled(value, "spine_figures.figures")


class MaterialityBlock(Strict):
    benchmark: Any
    band: Any
    spine_figures: SpineFigures

    @field_validator("benchmark")
    @classmethod
    def _benchmark(cls, value: Any) -> Any:
        return filled(value, "materiality.benchmark")

    @field_validator("band")
    @classmethod
    def _band(cls, value: Any) -> Any:
        return filled(value, "materiality.band")


class SamplingBlock(Strict):
    formula: str
    seed: int | str

    @field_validator("formula")
    @classmethod
    def _formula(cls, value: str) -> str:
        return str(filled(value, "sampling.formula")).strip()

    @field_validator("seed")
    @classmethod
    def _seed(cls, value: int | str) -> int | str:
        if isinstance(value, str):
            return str(filled(value, "sampling.seed")).strip()
        return value


class Periods(Strict):
    current: str
    prior: str

    @field_validator("current", "prior")
    @classmethod
    def _period(cls, value: str) -> str:
        return str(filled(value, "analytical_review.periods")).strip()

    @model_validator(mode="after")
    def _different(self) -> Periods:
        if self.current == self.prior:
            raise ValueError("analytical_review.periods.current and .prior must differ")
        return self


class AnalyticalReviewBlock(Strict):
    periods: Periods
    thresholds: Any

    @field_validator("thresholds")
    @classmethod
    def _thresholds(cls, value: Any) -> Any:
        return filled(value, "analytical_review.thresholds")


class SourceRowCitation(Strict):
    """Where a WorkMind figure came from: a source and a row in it."""

    source: str
    row: int | str
    detail: Any = None

    @field_validator("source")
    @classmethod
    def _source(cls, value: str) -> str:
        return str(filled(value, "source_row_citations[].source")).strip()

    @field_validator("row")
    @classmethod
    def _row(cls, value: int | str) -> int | str:
        if isinstance(value, str):
            return str(filled(value, "source_row_citations[].row")).strip()
        return value


class WorkmindBlock(Strict):
    source_row_citations: list[SourceRowCitation] = Field(min_length=1)


# --- the Financial Spine (Stage E, D32) --------------------------------------------------------
#
# Every figure is the string the Spine served, never a number the Binder computed (CAF D30);
# None means the Spine served no figure. The block is built by the Binder's own Spine-papers
# action from the Spine's answers, never accepted from an outside caller.


class SpineFsLine(Strict):
    """A presentation line of the area, as served."""

    head_id: str
    label: str
    current: str | None = None
    prior: str | None = None


class SpineLedgerRow(Strict):
    """One ledger's chain under a head, as the balances endpoint served it."""

    head_id: str
    ledger_key: str
    ledger_name: str
    parent_chain: list[str] = []
    unadjusted: str | None = None
    reclass: str | None = None
    corrections: str | None = None
    adjusted: str | None = None
    prior_closing: str | None = None


class SpineHeadTotal(Strict):
    """The Spine's own per-head totals (the Binder adds nothing up)."""

    head_id: str
    ledgers: int
    unadjusted: str | None = None
    adjusted: str | None = None
    prior_closing: str | None = None


class SpineAdjustmentLine(Strict):
    line_no: int | None = None
    ledger_key: str | None = None
    ledger_name: str | None = None
    head_id: str | None = None
    dr: str | None = None
    cr: str | None = None


class SpineAdjustment(Strict):
    """An adjustment as served: kind, status (proposed, accepted or refused, all kept),
    narration, the working paper and finding it names, who proposed and decided it."""

    adjustment_id: str
    kind: str
    status: str
    narration: str | None = None
    working_paper_ref: str | None = None
    finding_ref: str | None = None
    proposed_by: str | None = None
    proposed_at: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None
    lines: list[SpineAdjustmentLine] = []


class SpineBlock(Strict):
    """Provenance of a paper the Spine produced: which version, and what it served."""

    kind: Literal["lead_schedule", "adjustment_chain"]
    version_id: uuid.UUID
    version_label: str
    version_hash: str
    locked_at: datetime | None = None
    balances_hash: str | None = None
    tree_version: int | None = None
    # Lead schedule only.
    area: str | None = None
    lines: list[SpineFsLine] = []
    ledgers: list[SpineLedgerRow] = []
    head_totals: list[SpineHeadTotal] = []
    heads_without_ledgers: list[str] = []
    # Both kinds: the adjustments touching the area, or every adjustment of the version.
    adjustments: list[SpineAdjustment] = []
    # Adjustment chain only: the uncorrected schedule exactly as served.
    uncorrected: dict[str, Any] | None = None

    @field_validator("version_hash")
    @classmethod
    def _hash(cls, value: str) -> str:
        return str(filled(value, "spine.version_hash")).strip()

    @model_validator(mode="after")
    def _by_kind(self) -> SpineBlock:
        if self.kind == "lead_schedule":
            if not self.area or not self.area.strip():
                raise ValueError("a lead schedule names its area (spine.area)")
            if self.uncorrected is not None:
                raise ValueError("a lead schedule carries no uncorrected schedule")
        else:
            if self.area is not None:
                raise ValueError("the adjustment chain belongs to no single area")
            if self.lines or self.ledgers or self.head_totals or self.heads_without_ledgers:
                raise ValueError("the adjustment chain carries no area lines or ledgers")
            if self.uncorrected is None:
                raise ValueError("the adjustment chain carries the uncorrected schedule as served")
        return self


class Generated(Strict):
    source: Source
    module: str
    module_version: str | None = None
    run_id: str | None = None
    generated_at: datetime
    inputs: dict[str, Any]
    citations: list[Any]
    materiality: MaterialityBlock | None = None
    sampling: SamplingBlock | None = None
    analytical_review: AnalyticalReviewBlock | None = None
    workmind: WorkmindBlock | None = None
    spine: SpineBlock | None = None

    @field_validator("module")
    @classmethod
    def _module(cls, value: str) -> str:
        return str(filled(value, "module")).strip()

    @field_validator("module_version", "run_id")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("must not be blank when given")
        return text

    @field_validator("inputs")
    @classmethod
    def _inputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = filled(value, "inputs")
        return result

    @field_validator("citations")
    @classmethod
    def _citations(cls, value: list[Any]) -> list[Any]:
        result: list[Any] = filled(value, "citations")
        return result

    @model_validator(mode="after")
    def _one_block_for_the_source(self) -> Generated:
        blocks = {
            "materiality": self.materiality,
            "sampling": self.sampling,
            "analytical_review": self.analytical_review,
            "workmind": self.workmind,
            "spine": self.spine,
        }
        for name, block in blocks.items():
            if name == self.source:
                if block is None:
                    raise ValueError(f"source {self.source!r} needs its {name} block")
            elif block is not None:
                raise ValueError(f"a {self.source} paper carries no {name} block")
        if self.source == "workmind" and self.run_id is None:
            raise ValueError("a WorkMind paper carries its run id (spec 3C): run_id is required")
        return self


class GeneratedPaperIn(Strict):
    paper: PaperFields
    generated: Generated


class FreshnessOut(BaseModel):
    """Whether a Spine paper still matches the binder's linked version (Stage E, D32)."""

    state: Literal["current", "stale", "not_checked"]
    detail: str | None
    recorded_version_id: uuid.UUID | None
    recorded_version_label: str | None


class GenerationOut(BaseModel):
    """What the paper screen and the archive say about a generated paper."""

    id: uuid.UUID
    source: str
    module: str
    module_version: str | None
    run_id: str | None
    generated_at: datetime
    received_by: str
    received_at: datetime
    content_hash_at_intake: str
    spine_figures_check: str | None
    # D37: how the delivery's run was verified at intake (the WorkMind run read back), or None.
    run_verification: dict[str, Any] | None
    locked_fields: list[str]
    payload: dict[str, Any]
    # Stage E (D32): for a paper the Financial Spine produced, whether it still matches the
    # binder's linked version; None for every other source.
    freshness: FreshnessOut | None = None

    @classmethod
    def build(
        cls,
        row: WpGeneration,
        locked_fields: tuple[str, ...],
        freshness: FreshnessOut | None = None,
    ) -> GenerationOut:
        return cls(
            freshness=freshness,
            id=row.id,
            source=row.source,
            module=row.module,
            module_version=row.module_version,
            run_id=row.run_id,
            generated_at=row.generated_at,
            received_by=row.received_by,
            received_at=row.received_at,
            content_hash_at_intake=row.content_hash_at_intake,
            spine_figures_check=row.spine_figures,
            run_verification=row.run_verification,
            locked_fields=list(locked_fields),
            payload=dict(row.payload),
        )
