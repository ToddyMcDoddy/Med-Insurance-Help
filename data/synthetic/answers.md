# Ground truth for the synthetic data

All plans, insurers and bills are FICTIONAL. Plan layouts are inspired by common public plan-summary formats; no real text, logos or numbers were copied.

| Fictional insurer | Inspired by | PDF | Layout |
|---|---|---|---|
| UnifiedHealthcare | UnitedHealthcare | `plans/unifiedhealthcare_choice_plus_ppo_2000.pdf` (6 pp) | Summary-of-benefits Q&A table, in-network and out-of-network columns, copay table |
| PVS Health | CVS Health (Aetna) | `plans/pvs_healthsaver_hsa_5500.pdf` (5 pp) | HSA high-deductible overview, combined medical and drug deductible, no copays, **out-of-pocket max missing on purpose** |
| Advavate Health | Elevance Health (Anthem) | `plans/advavate_gold_ppo_25_1000_10.pdf` (6 pp) | Cost-coded plan name, costs in prose paragraphs, copays on last-page schedule |
| (adversarial) | | `plans/unifiedhealthcare_injected.pdf` (6 pp) | UnifiedHealthcare plus hidden prompt-injection text on page 4 |

## Extraction ground truth (machine-readable: `plans/expected_terms.json`)

**UnifiedHealthcare - Choice Plus PPO 2000**

| Term | Value | Page |
|---|---|---|
| deductible | 2000 | 3 |
| out_of_pocket_max | 6000 | 3 |
| coinsurance_pct | 20 | 4 |
| copay_primary_care | 30 | 5 |
| copay_specialist | 60 | 5 |
| copay_er | 350 | 5 |

_Distractors: family and out-of-network figures on page 3; $2,000 also appears in the page-6 coverage example._

**PVS Health - HealthSaver HSA 5500**

| Term | Value | Page |
|---|---|---|
| deductible | 5500 | 2 |
| out_of_pocket_max | not in document (leave empty) | - |
| coinsurance_pct | 30 | 3 |
| copay_primary_care | not in document (leave empty) | - |
| copay_specialist | not in document (leave empty) | - |
| copay_er | not in document (leave empty) | - |

_No copays exist. The out-of-pocket maximum is deliberately NOT stated (page 4 points to the Certificate). A correct extractor leaves them empty._

**Advavate Health - Gold PPO 25/1000/10%**

| Term | Value | Page |
|---|---|---|
| deductible | 1000 | 3 (page 1 also acceptable) |
| out_of_pocket_max | 4500 | 3 |
| coinsurance_pct | 10 | 4 (page 1 also acceptable) |
| copay_primary_care | 25 | 6 (page 1 also acceptable) |
| copay_specialist | 50 | 6 |
| copay_er | 250 | 6 |

_Plan name on page 1 encodes 25/1000/10%, so page 1 is also acceptable for those three. Copays are in the Schedule of Benefits on the last page. $380 on page 4 is a distractor._

## Estimate cases (machine-readable: `estimate_cases.json`)

Order: remaining deductible, then member share (coinsurance, or the flat copay for copay services, which skip the deductible), then cap the total at the remaining out-of-pocket max. Copays count toward the max. Amounts rounded to cents. When a needed term is missing, expect no dollar figure and the missing names listed. Compare `missing` as a set, not an ordered list.

| ID | Plan | Service | Allowed | Ded. met | OOP so far | Member pays | Plan pays | Missing | Why |
|---|---|---|---|---|---|---|---|---|---|
| uh-01 | unifiedhealthcare | MRI of the knee (coinsurance) | $1,200.00 | $500.00 | $500.00 | $1,200.00 | $0.00 | - | whole bill falls inside remaining deductible |
| uh-02 | unifiedhealthcare | Outpatient procedure (coinsurance) | $3,000.00 | $0.00 | $0.00 | $2,200.00 | $800.00 | - | deductible then 20% of the rest |
| uh-03 | unifiedhealthcare | Outpatient procedure (coinsurance) | $3,000.00 | $2,000.00 | $5,900.00 | $100.00 | $2,900.00 | - | 20% would be $600 but only $100 left under the cap |
| uh-04 | unifiedhealthcare | Primary care visit (copay) | $150.00 | $0.00 | $0.00 | $30.00 | $120.00 | - | copay skips deductible |
| uh-05 | unifiedhealthcare | Specialist visit (copay) | $200.00 | $0.00 | $0.00 | $60.00 | $140.00 | - | copay skips deductible |
| uh-06 | unifiedhealthcare | Emergency room visit (copay) | $2,500.00 | $0.00 | $0.00 | $350.00 | $2,150.00 | - | flat ER copay |
| uh-07 | unifiedhealthcare | Any covered service (coinsurance) | $800.00 | $2,000.00 | $6,000.00 | $0.00 | $800.00 | - | out-of-pocket max already reached |
| uh-08 | unifiedhealthcare | Primary care visit (copay) | $20.00 | $0.00 | $0.00 | $20.00 | $0.00 | - | copay larger than allowed amount |
| uh-09 | unifiedhealthcare | Free service (coinsurance) | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | - | allowed amount $0 |
| adv-01 | advavate | Lab work (coinsurance) | $800.00 | $0.00 | $0.00 | $800.00 | $0.00 | - | all inside the $1,000 deductible |
| adv-02 | advavate | Outpatient surgery (coinsurance) | $5,000.00 | $0.00 | $0.00 | $1,400.00 | $3,600.00 | - | deductible then 10% of the rest |
| adv-03 | advavate | Outpatient surgery (coinsurance) | $5,000.00 | $1,000.00 | $4,400.00 | $100.00 | $4,900.00 | - | 10% would be $500 but only $100 left under the cap |
| adv-04 | advavate | Primary care visit (copay) | $140.00 | $0.00 | $0.00 | $25.00 | $115.00 | - | copay skips deductible |
| pvs-01 | pvs | MRI (coinsurance) | $1,500.00 | $0.00 | $0.00 | n/a | n/a | out_of_pocket_max | out-of-pocket max not in the plan -> no dollar figure |
| pvs-02 | pvs | Primary care visit (copay) | $150.00 | $0.00 | $0.00 | n/a | n/a | copay_primary_care, out_of_pocket_max | plan has no copays -> no dollar figure |

## Bills (`bills/*.json`: each file has `bill`, `eob` or null, and `expected_flags`)

| File | Expected flags | What it tests |
|---|---|---|
| bill_duplicate.json | exact_duplicate ['L1', 'L2'] | Exact duplicate: L1 and L2 are identical. |
| bill_near_duplicate.json | near_duplicate ['L1', 'L2'] | Near duplicate: same provider, date and code, amount differs. |
| bill_same_service_twice.json | same_service_twice ['L1', 'L2'] | Same code on the same date billed by two different providers. |
| bill_eob_mismatch.json | eob_mismatch ['L1'] | L1: bill $85 is under the allowed amount but the EOB says the member owes $60. L2 matches. |
| bill_balance_billing.json | balance_billing ['L1'] | L1: provider bills the full $310 although the plan's allowed amount is $95 (member owes $19). |
| bill_clean.json | none | Nothing to flag. Different codes on the same date are normal; amounts match the EOB. |

Providers, dates and codes are made up. CPT-style codes are used only as plain labels. Flags mean "worth asking about", never an accusation.
