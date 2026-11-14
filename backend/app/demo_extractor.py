"""Fixture-only plan extraction for explicitly enabled synthetic demos."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .contract import PlanTerms, Sourced

_PLANS_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "plans"
_EXPECTED_TERMS_PATH = _PLANS_DIR / "expected_terms.json"


class DemoExtractionError(ValueError):
    """The upload does not match a bundled synthetic fixture."""


def _load_fixtures() -> dict[str, dict[str, Any]]:
    expected_terms = json.loads(_EXPECTED_TERMS_PATH.read_text())
    fixtures = {}
    for filename, plan in expected_terms.items():
        fixture_path = _PLANS_DIR / filename
        if fixture_path.is_file():
            digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
            fixtures[digest] = plan
    return fixtures


_FIXTURES_BY_SHA256 = _load_fixtures()


def extract_demo_plan(pdf_bytes: bytes) -> PlanTerms:
    """Return fixture terms only when upload bytes match a bundled PDF exactly."""
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    fixture = _FIXTURES_BY_SHA256.get(digest)
    if fixture is None:
        raise DemoExtractionError(
            "This PDF is not one of the bundled synthetic demo fixtures."
        )

    terms = {
        name: Sourced(value=term["value"], page=term["page"])
        for name, term in fixture["terms"].items()
    }
    return PlanTerms(
        insurer=fixture["insurer"],
        plan_name=fixture["plan_name"],
        **terms,
        not_found=fixture["not_found"],
        confirmed=False,
    )