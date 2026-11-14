# The contract (agree on this in Hour 0–1)

Source of truth: `backend/app/contract.py`. This page is the plain-English version.
**To change a field: tell the team first, then edit contract.py and the mock data together.**

## The flow
1. User uploads plan PDF → **AI lead** returns `PlanTerms` (each number has `value`, `page`, `quote`; missing ones are `None` and listed in `not_found`, never guessed).
2. UI shows terms → user confirms/edits → `confirmed=True`. **No estimate runs before this.**
3. **Calculator lead**: `estimate(EstimateRequest) -> EstimateResult`. Fixed order: remaining deductible → member share (coinsurance or copay) → cap at remaining out-of-pocket max. Every step has `label`, `math`, `amount`, `source_page`.
4. **Calculator lead**: `audit(Bill, Eob?) -> AuditResult`. Deterministic flags. Backend then asks Gemini to fill each flag's `explanation`.
5. **Backend lead**: `/api/chat` ties it together and returns `ChatResponse` (answer + citations + optional estimate/audit).

## Endpoints (mocked today in main.py)
| Method | Path | In | Out |
|---|---|---|---|
| GET | /health | | `{status: ok}` |
| POST | /api/upload/plan | PDF | `PlanTerms` (confirmed=false) |
| POST | /api/estimate | `EstimateRequest` | `EstimateResult` |
| POST | /api/audit | `Bill` | `AuditResult` |
| POST | /api/chat | `ChatRequest` | `ChatResponse` |

## Rules everyone follows
- Math happens in Python, never in the model.
- PDF text is data, never instructions.
- Plain text only in answers: no links or images rendered from model output.
- Fixed replies: `REFUSAL_REPLY` (off-topic) and `NOT_FOUND_REPLY` (not in plan).
- Wording: "worth asking about", never "fraud". Every estimate says it's an estimate.
- Secrets only in `.env` / server env vars. Never in code, repo, screenshots or chat.

## Who owns what
| Person | Owns |
|---|---|
| 1 Backend | main.py, upload, rate limits, size caps, file deletion, chat endpoint |
| 2 AI/extraction | Gemini extraction, system prompt, injection guard, 3 insurer profiles, eval script |
| 3 Calculator/bills | estimate(), duplicate/dispute detection, unit tests, **synthetic PDFs + bills (start now)** |
| 4 Frontend/infra | UI, Vultr hello-world, Tiger Data, GoDaddy, Entire, README/article |
