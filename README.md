# MediFit (working name)

AI health-insurance assistant: ask questions about your plan, estimate out-of-pocket cost
with every step shown, and audit medical bills for duplicate or disputable charges.
Synthetic demo data only. Not medical, legal or financial advice.

## Sponsor tools (fill in as we go)
| Tool | Used for | Status |
|---|---|---|
| Gemini API | PDF term extraction, chat, plain-language explanations | todo |
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
