# The contract (agree on this in Hour 0–1)

Source of truth: `backend/app/contract.py`. This page is the plain-English version.
**To change a field: tell the team first, then edit contract.py and the mock data together.**

## The flow
1. User uploads plan PDF → **AI lead** returns `PlanTerms` (each number has `value`, `page`, `quote`; missing ones are `None` and listed in `not_found`, never guessed).
2. UI shows terms → user confirms/edits → `confirmed=True`. **No estimate runs before this.**
3. **Calculator lead**: `estimate(EstimateRequest) -> EstimateResult`. Fixed order: remaining deductible → member share (coinsurance or copay) → cap at remaining out-of-pocket max. Every step has `label`, `math`, `amount`, `source_page`.
4. **Calculator lead**: `audit(Bill, Eob?) -> AuditResult`. Deterministic flags. Backend then asks Gemini to fill each flag's `explanation`.
5. **Backend lead**: `/api/chat` ties it together and returns `ChatResponse` (answer + citations + optional estimate/audit).

## Endpoints
| Method | Path | In | Out |
|---|---|---|---|
| GET | /health | | `{status: ok}` |
| POST | /api/upload/plan | `multipart/form-data` with file field `file` (PDF) | `PlanTerms` (confirmed=false, once extraction is connected) |
| POST | /api/estimate | `EstimateRequest` | `EstimateResult` |
| POST | /api/audit | `Bill` | `AuditResult` |
| POST | /api/chat | `ChatRequest` | `ChatResponse` |

### Plan upload
Send a PDF as the required multipart field named `file`. The backend reads at most
`MAX_UPLOAD_MB` plus one byte (default 5 MB). Empty, malformed, encrypted, textless,
or unknown demo PDFs receive HTTP 400; oversized files receive HTTP 413. Uploads over
`RATE_LIMIT_PER_MIN` (default 20 per minute) receive HTTP 429 with a `Retry-After`
header. A readable PDF receives HTTP 501 with `Plan extraction is not connected yet.`
when extraction is disabled.

Set `EXTRACTOR_MODE=demo` to enable fixture extraction. Demo mode recognizes only the
bundled synthetic PDFs by SHA-256 of their bytes, independent of the uploaded filename.
It returns the matching `PlanTerms` with `confirmed=false` and the response header
`X-MediFit-Extraction-Mode: demo`. These are fixture answers from `expected_terms.json`,
not AI extraction or evidence of extraction accuracy. Unknown PDFs are rejected; no
sample plan is substituted. Leave `EXTRACTOR_MODE` unset or set it to `disabled` to
keep the HTTP 501 behavior. Demo setup: `cd backend && EXTRACTOR_MODE=demo .venv/bin/uvicorn app.main:app --reload`.

The rate limiter uses the server-provided direct client address and monotonic time. It
keeps bounded in-memory state and is suitable for a single process only; limits are
not shared across workers or server instances. Behind a reverse proxy, the proxy
address is used unless trusted-proxy configuration is added. User-supplied forwarding
headers are ignored, so do not assume per-user limits behind an unconfigured proxy.

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
