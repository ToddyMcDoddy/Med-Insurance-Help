# Synthetic data (DONE: generated and checked)

Everything here is FAKE. No real names, member IDs, SSNs or birth dates. Insurer names are fictional look-alikes
used only to test our software; layouts are inspired by common public plan-summary formats, with no real logos, text or numbers.
Every PDF page carries a "SYNTHETIC SAMPLE" footer.

| Fictional insurer | Inspired by | Layout quirk |
|---|---|---|
| UnifiedHealthcare | UnitedHealthcare | Clean Q&A table, in-network and out-of-network columns, copay table |
| PVS Health | CVS Health (Aetna) | HSA high-deductible plan, no copays, **out-of-pocket max missing on purpose** |
| Advavate Health | Elevance Health (Anthem) | Cost-coded plan name, costs in prose, copays on the last-page schedule |

Files: `plans/*.pdf` (3 plans + `unifiedhealthcare_injected.pdf` with hidden prompt-injection text), `plans/expected_terms.json`
(extraction ground truth with pages), `estimate_cases.json` (15 cases with expected answers), `bills/*.json` (6 bills,
each with `bill`, `eob` or null, and `expected_flags`), and `answers.md` (human-readable version of all of it).

Used by: Person 2 (extraction and eval), Person 3 (calculator and audit tests), Person 1 and 4 (demo data).
