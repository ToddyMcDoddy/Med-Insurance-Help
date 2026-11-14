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
| GET | /api/services | Optional `q` (service ID, name, or alias) | Illustrative service catalog |
| POST | /api/chat | `ChatRequest` | `ChatResponse` |
| PUT | /api/chat/sessions/{session_id}/context | plan terms, document page text, explicit human confirmation | context acknowledgement |

### Plan upload
Send a PDF as the required multipart field named `file`. The backend reads at most
`MAX_UPLOAD_MB` plus one byte (default 5 MB). Empty, malformed, encrypted, textless,
or unknown demo PDFs receive HTTP 400; oversized files receive HTTP 413. Uploads over
`RATE_LIMIT_PER_MIN` (default 20 per minute) receive HTTP 429 with a `Retry-After`
header. With extraction disabled, a readable PDF receives HTTP 501 with
`Plan extraction is not connected yet.` With Gemini configured but unavailable or
misconfigured, the endpoint returns a generic HTTP 502 or 503 without provider details.

Set `EXTRACTOR_MODE=demo` to enable fixture extraction. Demo mode recognizes only the
bundled synthetic PDFs by SHA-256 of their bytes, independent of the uploaded filename.
It returns the matching `PlanTerms` with `confirmed=false` and the response header
`X-MediFit-Extraction-Mode: demo`. These are fixture answers from `expected_terms.json`,
not AI extraction or evidence of extraction accuracy. Unknown PDFs are rejected; no
sample plan is substituted. Leave `EXTRACTOR_MODE` unset or set it to `disabled` to
keep the HTTP 501 behavior. Demo setup: `cd backend && EXTRACTOR_MODE=demo .venv/bin/uvicorn app.main:app --reload`.

Set `EXTRACTOR_MODE=gemini` to run the Gemini plan extractor. It consumes validated
page text in a worker thread and returns `PlanTerms` with `confirmed=false`; it does
not use the synthetic expected-terms file. The existing path-based extractor command
remains available. Live upload setup: `cd backend && EXTRACTOR_MODE=gemini .venv/bin/uvicorn app.main:app --reload`, with `GEMINI_API_KEY` set in the server environment.

For the synthetic demo, set `EXTRACTOR_DEMO_FALLBACK=1` alongside `EXTRACTOR_MODE=gemini`.
On extraction failure, an exact bundled PDF match returns fixture terms with
`X-MediFit-Extraction-Mode: demo`. Other PDFs retain the provider error.

To test the upload-to-chat flow, POST a bundled PDF to `/api/upload/plan` using the
multipart field `file`. After the user reviews and confirms the returned terms, send
`PUT /api/chat/sessions/{session_id}/context` with those terms, `confirmed: true`,
`plan_document_id`, and the extracted page text as `documents`. Then POST
`/api/chat` using the same `session_id` and explicit `estimate_input` where needed.
The upload endpoint does not confirm the plan or automatically attach session context.

The rate limiter uses the server-provided direct client address and monotonic time. It
keeps bounded in-memory state and is suitable for a single process only; limits are
not shared across workers or server instances. Behind a reverse proxy, the proxy
address is used unless trusted-proxy configuration is added. User-supplied forwarding
headers are ignored, so do not assume per-user limits behind an unconfigured proxy.

### Chat sessions and tools
Before chatting about a plan, associate its terms and extracted pages with a session:
`PUT /api/chat/sessions/{session_id}/context` with JSON fields `plan`,
`plan_document_id`, `documents` (each has `doc_id`, 1-based `page`, and `text`),
`confirmed`, and optional `progress`. The explicit `confirmed` field is controlled by
the application after the user confirms the displayed terms; chat tools cannot change
it. Source-term pages must exist in the associated plan document. Session IDs isolate
context; sessions expire after 60 minutes and the process stores at most 1,000. Context
is capped by `CHAT_MAX_DOCUMENT_PAGES` (default 200) and `CHAT_MAX_CONTEXT_CHARS`
(default 100,000). This storage is in memory and is not shared across workers or restarts.

`POST /api/chat` keeps the existing `session_id` and `message` fields. For an estimate,
also supply `estimate_input` with `service`, `allowed_amount`, `kind`, and `copay_type`
when applicable. These are explicit caller inputs; Gemini cannot invent them. The
`estimate_cost` tool calls the Python calculator, which enforces confirmation and
required terms. Plan-document searches return citations only for stored document/page
pairs. Document text is untrusted data and cannot change system rules or confirmation.
Out-of-scope requests use `REFUSAL_REPLY`; missing evidence uses `NOT_FOUND_REPLY`.

Use `/api/audit` for deterministic bill flags and plain-language explanations.
Service prices are synthetic demo values. Chat uses the server-side `GEMINI_API_KEY`; missing
configuration returns HTTP 503 and provider/tool failures return HTTP 502. Limits:
`MAX_OUTPUT_TOKENS` (default 800), `MAX_TOOL_CALLS_PER_TURN` (default 3), and
`MAX_TURNS_PER_SESSION` (default 30). Tool calls exceeding the configured turn cap are
rejected. Context/session limits are per process; live multi-worker deployments need
shared session storage and coordinated limits.

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

Live-tested chat configuration: set `GEMINI_MODEL=gemini-3.6-flash` in the server environment. The upload → confirm → chat test returned member_pays=2200 and plan_pays=800 for a $3000 allowed amount.
