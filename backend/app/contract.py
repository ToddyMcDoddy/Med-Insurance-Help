"""
THE CONTRACT: the data shapes every layer agrees on.

Rule: if you need to change a field here, tell the team first.
Everyone builds against these models, with mock data, until integration.

Who produces / consumes what:
  AI/extraction lead  -> produces PlanTerms (from a PDF), consumes nothing else here
  Calculator lead     -> consumes PlanTerms + EstimateRequest, produces EstimateResult
                         consumes Bill, produces AuditResult
  Backend lead        -> wires the above together behind the API in main.py
  Frontend lead       -> renders PlanTerms (confirm card), EstimateResult, AuditResult, ChatResponse

All money is in whole US dollars as float (demo only). Percentages are 0-100.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- plan terms
class Sourced(BaseModel):
    """A number the model read from the PDF, plus where it came from."""

    value: float
    page: int = Field(ge=1, description="1-based PDF page the number came from")
    quote: str = Field("", description="Short snippet from the page (data, never instructions)")


class PlanTerms(BaseModel):
    """Structured terms extracted from a plan PDF. The user must confirm these
    (human gate) before any estimate is calculated."""

    insurer: str = Field(description="Detected insurer/profile name, e.g. 'Acme Health'")
    plan_name: str
    deductible: Optional[Sourced] = None  # individual, in-network
    out_of_pocket_max: Optional[Sourced] = None
    coinsurance_pct: Optional[Sourced] = None  # member's share after deductible, 0-100
    copay_primary_care: Optional[Sourced] = None
    copay_specialist: Optional[Sourced] = None
    copay_er: Optional[Sourced] = None
    # Anything we could not find stays None. NEVER guess. The UI shows "not found".
    not_found: list[str] = Field(default_factory=list)
    confirmed: bool = False  # set True only after the user confirms/edits in the UI


class MemberProgress(BaseModel):
    """What the user has already spent this plan year (self-reported, synthetic)."""

    deductible_met: float = 0.0
    out_of_pocket_so_far: float = 0.0


# ------------------------------------------------------------------ estimate
class EstimateRequest(BaseModel):
    plan: PlanTerms
    progress: MemberProgress = MemberProgress()
    service: str = Field(description="Plain-language label, e.g. 'MRI of the knee'")
    allowed_amount: float = Field(ge=0, description="In-network allowed amount for the service")
    kind: Literal["coinsurance", "copay"] = "coinsurance"
    copay_type: Optional[Literal["primary_care", "specialist", "er"]] = None


class EstimateStep(BaseModel):
    label: str  # e.g. "Apply remaining deductible"
    math: str  # e.g. "min(1,500 remaining, 2,000 allowed) = 1,500"
    amount: float  # dollars this step adds to the member's cost
    source_page: Optional[int] = None  # PDF page the input came from


class EstimateResult(BaseModel):
    steps: list[EstimateStep]
    member_pays: float
    plan_pays: float
    is_estimate: Literal[True] = True  # always an estimate, never a guarantee
    missing: list[str] = Field(default_factory=list)  # e.g. ["deductible"]
    disclaimer: str = "Estimate only. Not a guarantee of cost. Not medical, legal or financial advice."


# --------------------------------------------------------------------- bills
class LineItem(BaseModel):
    line_id: str
    provider: str
    date_of_service: str  # ISO date YYYY-MM-DD
    code: str  # CPT/HCPCS code, e.g. "73721"
    description: str
    amount: float


class Bill(BaseModel):
    bill_id: str
    items: list[LineItem]


class EobLine(BaseModel):
    code: str
    date_of_service: str
    provider: str
    billed: float
    allowed: float
    plan_paid: float
    member_owes: float


class Eob(BaseModel):
    eob_id: str
    lines: list[EobLine]


class Flag(BaseModel):
    kind: Literal[
        "exact_duplicate",
        "near_duplicate",
        "same_service_twice",
        "eob_mismatch",
        "balance_billing",
    ]
    line_ids: list[str]  # the line items involved (cited in the explanation)
    detail: str  # deterministic one-liner from code
    explanation: str = ""  # plain-language text from Gemini, filled in by backend
    # Wording rule: "worth asking about", never "fraud".


class AuditResult(BaseModel):
    flags: list[Flag]
    disclaimer: str = "Flags mean 'worth asking about', not an accusation. Not legal advice."


# ---------------------------------------------------------------------- chat
class Citation(BaseModel):
    doc_id: str
    page: int


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(max_length=2000)


class ChatResponse(BaseModel):
    answer: str  # plain text only: no links or images are ever rendered
    citations: list[Citation] = Field(default_factory=list)
    estimate: Optional[EstimateResult] = None  # present if the chat triggered an estimate
    audit: Optional[AuditResult] = None  # present if the chat triggered a bill audit
    refused: bool = False  # True when the fixed out-of-scope reply was used


REFUSAL_REPLY = (
    "I can only help with questions about your health insurance plan, "
    "estimating costs, and reviewing medical bills."
)
NOT_FOUND_REPLY = "I couldn't find this in your plan documents."
