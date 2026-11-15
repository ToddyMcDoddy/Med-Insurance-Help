# Unsurance

AI health-insurance assistant: upload your plan PDF, ask questions about your coverage, see an out-of-pocket estimate with every step of the math, and check medical bills for duplicate or disputable charges.

**Live demo:** https://66-42-92-150.sslip.io (fallback: http://66.42.92.150/)

Synthetic demo data only. Please do not upload real insurance documents. Not medical, legal or financial advice. Estimates are not a guarantee of cost.

(The repository was renamed to `idontunderstandmymedinsurance`; "Unsurance" is the app's name.)

## What it does
- **Reads your plan.** Gemini turns the plan PDF into structured terms (deductible, coinsurance, copays, out-of-pocket max), each with the page it came from. You confirm the terms before anything is calculated.
- **Answers questions.** Plain-language answers grounded in your plan, with page citations.
- **Estimates cost.** A plain Python function (not the model) does the math in a fixed order and shows every step.
- **Reviews bills.** Code finds duplicate and disputable charges; Gemini explains them in plain language and suggests a question you can ask the billing office. Flags mean "worth asking about", never an accusation.

## Sponsor tools
| Tool | Used for | Status |
|---|---|---|
| Gemini API | PDF term extraction, chat, plain-language explanations, bill explanations, eval | In use |
| Vultr | Hosts the app: one Ubuntu VM, FastAPI service, Caddy for HTTPS; the Gemini key is a server environment variable | In use |
| GoDaddy | Domain for the app | Planned, not connected yet (the app runs on a free sslip.io HTTPS address) |
| Tiger Data | Database | Not used. We chose in-memory sessions for the demo. |
| Entire | AI coding session recording | Not used |
| DEV | Project article | Draft written, not published yet |

## How it is built
- **Backend:** FastAPI (Python), one worker, run as a systemd service behind Caddy.
- **Front end:** plain JavaScript, served by the backend from `site/` (prebuilt; its source is not in this repo).
- **AI:** Gemini through the `google-genai` library. The demo server runs `gemini-3.5-flash-lite` on a free-tier key.
- **Sessions:** held in server memory, so a server restart clears them.

## Accessibility
Keyboard navigation and a skip link, voice input ("Speak" button), a high-contrast option, a colorblind-friendly option (blue and orange palette), and text labels on status badges so meaning never depends on color alone.

## Safety and privacy
- Synthetic data only; the app does not ask for names, member IDs or other personal details.
- PDF text is treated as data, never as instructions (tested with a PDF that hides an injection attempt).
- Model output is shown as plain text: links and images are not rendered.
- Server-side limits: per-IP rate limit, upload size cap, and a cap on tool calls per chat turn.
- The API key lives only in a server environment variable or a gitignored `.env`.

## Run the backend
    cd backend
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp ../.env.example ../.env     # then fill in locally, never commit
    uvicorn app.main:app --reload  # open http://127.0.0.1:8000/ for the app
    python3 -m pytest -q

## Layout
- `backend/app/contract.py`: the shared data shapes (read `docs/CONTRACT.md`)
- `site/`: the front end and accessibility add-ons
- `data/synthetic/`: fake plan PDFs and bills (spec in `SPEC.md`)
- `eval/`: test cases and the harness

## AI layer (Gemini)

Gemini is our only AI model. It is used in three places, and in each one code, not the model, has the last word.

1. **Reading the plan.** `extract_plan_terms` turns the plan PDF into structured terms (deductible, coinsurance, copays, out-of-pocket max, limits), each with the page it came from. If a number is not on the cited page, code drops it. If a term is missing, it stays "not found" and is never guessed. The user confirms the terms before any estimate is calculated.
2. **Chat.** `answer_question` answers only from the user's plan and confirmed terms, and cites pages. Off-topic requests get a fixed refusal, missing info gets a fixed "couldn't find this in your plan" reply, and links and images are stripped from answers. The model never does estimate math; a plain function does.
3. **Bills.** Duplicate and dispute flags are found by code. `explain_flags` and `draft_dispute_letter` only put them in plain language ("worth asking about", never an accusation). Letters keep placeholders for the user's details. If Gemini fails, code-written text is used instead. The live web app currently shows the explanation and a suggested question; the letter-drafting function is part of the AI layer but is not shown in the web app yet.

**Prompt-injection safety.** All PDF text is treated as data, never as instructions. We test this with a plan PDF that has hidden text on page 4 trying to set the deductible to $0, say everything is covered, and reveal the instructions. The model ignored it.

**Insurer profiles ("learning" without training).** The app detects the insurer from the first pages by keywords and gives extraction layout hints for that insurer. The design updates a profile only from numbers the user has confirmed (no PDF text, no personal info), and insurer averages are never used in a user's own estimate. In this demo the profile updating is not wired into the live app yet; profiles are seeded with our synthetic plans.

**Models and limits.** Preferred model: `gemini-3.6-flash` (the live demo server runs `gemini-3.5-flash-lite` on a free-tier key), with other Gemini models as automatic fallbacks if one is busy or out of quota. The API key lives only in a server environment variable or a gitignored `.env`.

## What we tested
- **Backend tests:** 93 automated tests pass (`python3 -m pytest -q`).
- **Evaluation:** 16 synthetic cases (4 plan extraction, 10 chat, 2 bill audits), including prompt injection, off-topic, reveal-the-prompt and missing-data cases. Each case is run 3 times with plain-code checks (no AI judge). Latest result (model rotation was active, so some calls may have run on backup Gemini models when a free-tier daily limit was hit): **pass@1 100%, pass^3 100%** (16/16 cases, 48/48 attempts).
- **By hand on the live site:** upload a plan, confirm terms, ask questions with citations, run estimates, review a sample bill.

    python3 eval/run_eval.py --runs 3

## Known limits
- The eval set is small and synthetic, and it tests the AI functions directly, not the full web app. One chat check (`chat-pvs-oop`) was loosened after we confirmed the plan text really says the maximum is printed in the Certificate of Coverage rather than given as a number.
- Gemini's free tier allows roughly 20 requests per day per model, so heavy use can hit the limit.
- Citations can be a page range rather than one exact page.
- Estimate prices come from a small illustrative list (`/api/services`), not real insurer rates.
- Sessions are lost when the server restarts.
- The colorblind mode was checked by eye, not with a simulator.

