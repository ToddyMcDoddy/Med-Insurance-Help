# MediFit (working name)

AI health-insurance assistant: ask questions about your plan, estimate out-of-pocket cost
with every step shown, and audit medical bills for duplicate or disputable charges.
Synthetic demo data only. Not medical, legal or financial advice.

## Sponsor tools (fill in as we go)
| Tool | Used for | Status |
|---|---|---|
| Gemini API | PDF term extraction, chat, plain-language explanations | in use: extraction, chat, bill explanations, eval |
| Vultr | Backend hosting, keys as server env vars | todo |
| GoDaddy | Domain for the app | todo |
| Tiger Data | Postgres DB for plans/preferences | todo |
| Entire | AI coding collaboration | todo |
| DEV | Project article | todo |

## Run the backend
    cd backend
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp ../.env.example ../.env     # then fill in locally, never commit
    uvicorn app.main:app --reload  # open http://127.0.0.1:8000/health
    python3 -m pytest -q

## Layout
- `backend/app/contract.py`: the shared data shapes (read `docs/CONTRACT.md`)
- `data/synthetic/`: fake plan PDFs and bills (spec in `SPEC.md`)
- `eval/`: 10+ test cases and the harness

## AI layer (Gemini)

Gemini is our only AI model. It is used in three places, and in each one code, not the model, has the last word.

1. **Reading the plan.** `extract_plan_terms` turns the plan PDF into structured terms (deductible, coinsurance, copays, out-of-pocket max, limits), each with the page it came from. If a number is not on the cited page, code drops it. If a term is missing, it stays "not found" and is never guessed. The user confirms the terms before any estimate is calculated.
2. **Chat.** `answer_question` answers only from the user's plan and confirmed terms, and cites pages. Off-topic requests get a fixed refusal, missing info gets a fixed "couldn't find this in your plan" reply, and links and images are stripped from answers. The model never does estimate math; a plain function does.
3. **Bills.** Duplicate and dispute flags are found by code. `explain_flags` and `draft_dispute_letter` only put them in plain language ("worth asking about", never an accusation). Letters keep placeholders for the user's details. If Gemini fails, code-written text is used instead.

**Prompt-injection safety.** All PDF text is treated as data, never as instructions. We test this with a plan PDF that has hidden text on page 4 trying to set the deductible to $0, say everything is covered, and reveal the instructions. The model ignored it.

**Insurer profiles ("learning" without training).** The app detects the insurer from the first pages by keywords and gives extraction layout hints for that insurer. A profile is updated only from numbers the user has confirmed (no PDF text, no personal info). Profiles are currently held in memory and seeded with our synthetic plans. Insurer averages are never used in a user's own estimate.

**Models and limits.** Main model: `gemini-3.6-flash`, with other Gemini models as automatic fallbacks if one is busy or out of quota. The API key lives only in a server environment variable or a gitignored `.env`.

### Evaluation
16 synthetic cases (4 plan extraction, 10 chat, 2 bill audits), including prompt injection, off-topic, reveal-the-prompt and missing-data cases. Each case is run 3 times with plain-code checks (no AI judge). Latest result on `gemini-3.6-flash`: **pass@1 100%, pass^3 100%** (16/16 cases, 48/48 attempts).

Honest limits: the set is small and synthetic, and it tests the AI functions directly, not the full web app. One chat check (`chat-pvs-oop`) was loosened after we confirmed the plan text really says the maximum is printed in the Certificate of Coverage rather than given as a number.

    python3 eval/run_eval.py --runs 3
