"""Deterministic, plan-grounded cost estimates."""
from __future__ import annotations

from .contract import EstimateRequest, EstimateResult, EstimateStep, Sourced


def _dollars(amount: float) -> str:
    return f"${amount:,.2f}".rstrip("0").rstrip(".")


def _require_terms(req: EstimateRequest) -> dict[str, Sourced]:
    if req.kind == "coinsurance":
        names = ("deductible", "coinsurance_pct", "out_of_pocket_max")
    else:
        names = (f"copay_{req.copay_type}", "out_of_pocket_max")

    missing = [name for name in names if getattr(req.plan, name) is None]
    if missing:
        raise ValueError(
            "Cannot calculate an estimate because required plan term(s) are missing: "
            + ", ".join(missing)
            + ". Confirm a plan with these terms or provide the missing values."
        )
    return {name: getattr(req.plan, name) for name in names}


def estimate(req: EstimateRequest) -> EstimateResult:
    """Calculate member and plan payment from confirmed, sourced plan terms."""
    if not req.plan.confirmed:
        raise ValueError("Plan terms must be confirmed before estimating costs.")

    terms = _require_terms(req)
    allowed = req.allowed_amount
    steps: list[EstimateStep] = []

    if req.kind == "coinsurance":
        deductible = terms["deductible"]
        coinsurance = terms["coinsurance_pct"]
        remaining_deductible = max(0.0, deductible.value - req.progress.deductible_met)
        deductible_applied = min(allowed, remaining_deductible)
        after_deductible = allowed - deductible_applied
        coinsurance_amount = after_deductible * coinsurance.value / 100

        steps.append(
            EstimateStep(
                label="Apply remaining deductible",
                math=(
                    f"min({_dollars(remaining_deductible)} remaining, "
                    f"{_dollars(allowed)} allowed) = {_dollars(deductible_applied)}"
                ),
                amount=deductible_applied,
                source_page=deductible.page,
            )
        )
        steps.append(
            EstimateStep(
                label="Apply coinsurance after deductible",
                math=(
                    f"{coinsurance.value:g}% x {_dollars(after_deductible)} "
                    f"after deductible = {_dollars(coinsurance_amount)}"
                ),
                amount=coinsurance_amount,
                source_page=coinsurance.page,
            )
        )
        before_cap = deductible_applied + coinsurance_amount
    else:
        copay = terms[f"copay_{req.copay_type}"]
        copay_amount = min(allowed, copay.value)
        steps.append(
            EstimateStep(
                label="Apply selected service copay (deductible does not apply)",
                math=(
                    f"min({_dollars(copay.value)} copay, {_dollars(allowed)} allowed) "
                    f"= {_dollars(copay_amount)}"
                ),
                amount=copay_amount,
                source_page=copay.page,
            )
        )
        before_cap = copay_amount

    out_of_pocket_max = terms["out_of_pocket_max"]
    remaining_max = max(0.0, out_of_pocket_max.value - req.progress.out_of_pocket_so_far)
    member_pays = min(before_cap, remaining_max, allowed)
    cap_adjustment = member_pays - before_cap
    steps.append(
        EstimateStep(
            label="Cap at remaining out-of-pocket maximum",
            math=(
                f"min({_dollars(before_cap)} calculated, {_dollars(remaining_max)} "
                f"remaining, {_dollars(allowed)} allowed) = {_dollars(member_pays)}"
            ),
            amount=cap_adjustment,
            source_page=out_of_pocket_max.page,
        )
    )

    return EstimateResult(
        steps=steps,
        member_pays=member_pays,
        plan_pays=allowed - member_pays,
    )