"""Insurer detection and profiles: the 'learning' part, with no model training.

Owner: AI/extraction lead. Detection is plain keyword matching (no Gemini call).
A profile gives the extractor a short layout hint and remembers the typical range of each term,
learned ONLY from numbers on plans the user has CONFIRMED (never PDF text, never personal info).
Profiles are seeded with the synthetic demo plans. Storage is in memory for now; the backend
or infra owner can swap _OBSERVED for a Tiger Data table later.
"""
import re
from collections import defaultdict

FIELDS = (
    "deductible",
    "out_of_pocket_max",
    "coinsurance_pct",
    "copay_primary_care",
    "copay_specialist",
    "copay_er",
)

PROFILES = {
    "unifiedhealthcare": {
        "name": "UnifiedHealthcare",
        "keywords": ["unifiedhealthcare"],
        "hint": (
            "This insurer uses a summary-of-benefits layout: a Q&A table with in-network and out-of-network columns, "
            "and a separate copay table. Use the individual in-network figures."
        ),
    },
    "pvs": {
        "name": "PVS Health",
        "keywords": ["pvshealth"],
        "hint": (
            "This insurer sells high-deductible HSA plans with one combined medical and drug deductible. "
            "Such plans often have no flat copays and may not state an out-of-pocket maximum. "
            "Leave any term empty unless this document states it."
        ),
    },
    "advavate": {
        "name": "Advavate Health",
        "keywords": ["advavate"],
        "hint": (
            "This insurer puts costs in prose paragraphs, and the plan name encodes the copay, deductible and coinsurance "
            "(for example 25/1000/10%). Copays are usually listed in a schedule of benefits near the end."
        ),
    },
}

# Numbers seen on user-confirmed plans. Seeded from the synthetic demo plans.
_OBSERVED = defaultdict(lambda: defaultdict(list))
_SEED = {
    "unifiedhealthcare": dict(deductible=2000, out_of_pocket_max=6000, coinsurance_pct=20,
                              copay_primary_care=30, copay_specialist=60, copay_er=350),
    "pvs": dict(deductible=5500, coinsurance_pct=30),
    "advavate": dict(deductible=1000, out_of_pocket_max=4500, coinsurance_pct=10,
                     copay_primary_care=25, copay_specialist=50, copay_er=250),
}
for _key, _vals in _SEED.items():
    for _field, _v in _vals.items():
        _OBSERVED[_key][_field].append(float(_v))


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def detect_insurer(pages):
    """Return a profile key like 'pvs', or None. Looks only at the first two pages."""
    text = _norm(" ".join(pages[:2]))
    for key, p in PROFILES.items():
        if any(_norm(k) in text for k in p["keywords"]):
            return key
    return None


def profile_name(key):
    return PROFILES[key]["name"] if key in PROFILES else None


def profile_hint(key):
    """A short layout hint for the extractor, or '' when the insurer is unknown."""
    return PROFILES[key]["hint"] if key in PROFILES else ""


def observe(key, terms):
    """Learn from a plan the user CONFIRMED. Stores numbers only."""
    if key not in PROFILES or not getattr(terms, "confirmed", False):
        return
    for field in FIELDS:
        t = getattr(terms, field)
        if t is not None:
            _OBSERVED[key][field].append(float(t.value))


def typical_ranges(key):
    """{field: (min, max)} over confirmed numbers seen for this insurer."""
    return {f: (min(v), max(v)) for f, v in _OBSERVED.get(key, {}).items() if v}
