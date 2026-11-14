"""Eval harness: runs known-answer cases several times and reports pass@1 and pass^k side by side.

Run from the repo root:
    python3 eval/run_eval.py --runs 3         full eval (about 18 Gemini calls per run)
    python3 eval/run_eval.py --runs 1         cheap trial
    python3 eval/run_eval.py --only chat      only cases whose id or category contains "chat"
    python3 eval/run_eval.py --report         just print the report from saved results
    python3 eval/run_eval.py --fresh          delete saved results and start over

Every check is plain code (no AI judge). Progress is saved after every call, so if Gemini runs out of
quota the harness stops cleanly and you can run it again later: it resumes where it left off.

pass@1 = share of single attempts that passed.
pass^k = share of cases that passed ALL k attempts (how reliable the case is).
"""
import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
CASES_FILE = ROOT / "eval" / "cases" / "cases.json"
RESULTS_FILE = ROOT / "eval" / "results" / "results.json"
PLANS = ROOT / "data" / "synthetic" / "plans"
BILLS = ROOT / "data" / "synthetic" / "bills"
FIELDS = ("deductible", "out_of_pocket_max", "coinsurance_pct", "copay_primary_care", "copay_specialist", "copay_er")


class StopEval(Exception):
    """Gemini is unavailable or out of quota. Stop cleanly; results so far are saved."""


# ----------------------------------------------------------------------------- checks (plain code)
def check_extraction(result, exp):
    problems = []
    if result.insurer != exp["insurer"]:
        problems.append(f"insurer {result.insurer!r} != {exp['insurer']!r}")
    for f in FIELDS:
        got = getattr(result, f)
        if f in exp["terms"]:
            e = exp["terms"][f]
            ok_pages = {e["page"], *e.get("also_acceptable_pages", [])}
            if got is None:
                problems.append(f"{f}: missing (expected {e['value']})")
            elif abs(got.value - e["value"]) > 0.01:
                problems.append(f"{f}: {got.value} != {e['value']}")
            elif got.page not in ok_pages:
                problems.append(f"{f}: page {got.page} not in {sorted(ok_pages)}")
        elif got is not None:
            problems.append(f"{f}: should be empty but got {got.value}")
    if set(result.not_found) != set(exp.get("not_found", [])):
        problems.append(f"not_found {sorted(result.not_found)} != {sorted(exp.get('not_found', []))}")
    return problems


def check_chat(resp, ex, not_found_reply):
    a, problems = resp.answer, []
    if "refused" in ex and resp.refused != ex["refused"]:
        problems.append(f"refused={resp.refused}, expected {ex['refused']}")
    if ex.get("reply") == "not_found" and a != not_found_reply:
        problems.append(f"expected the fixed not-found reply, got: {a[:80]!r}")
    for pat in ex.get("must_match", []):
        if not re.search(pat, a):
            problems.append(f"answer lacks /{pat}/")
    if ex.get("must_match_any") and not any(re.search(p, a) for p in ex["must_match_any"]):
        problems.append(f"answer matches none of {ex['must_match_any']}")
    for pat in ex.get("must_not_match", []):
        if re.search(pat, a):
            problems.append(f"answer wrongly matches /{pat}/")
    if ex.get("no_dollar") and re.search(r"\$\s?\d", a):
        problems.append("answer contains a dollar amount")
    missing = set(ex.get("cites", [])) - {c.page for c in resp.citations}
    if missing:
        problems.append(f"missing citation for page(s) {sorted(missing)}")
    return problems


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


# ----------------------------------------------------------------------------- running cases
def run_case(case, app, expected, pages_cache):
    def pages(pdf):
        if pdf not in pages_cache:
            pages_cache[pdf] = app["read_pages"](str(PLANS / pdf))
        return pages_cache[pdf]

    try:
        if case["type"] == "extraction":
            result = app["extract_plan_terms"](str(PLANS / case["pdf"]))
            return check_extraction(result, expected[case["expected_from"]])

        if case["type"] == "chat":
            resp = app["answer_question"](case["question"], pages(case["pdf"]))
            return check_chat(resp, case["expect"], app["NOT_FOUND_REPLY"])

        if case["type"] == "bill":
            data = json.load(open(BILLS / case["file"]))
            bill = app["Bill"](**data["bill"])
            eob = app["Eob"](**data["eob"]) if data.get("eob") else None
            flags = [
                app["Flag"](kind=f["kind"], line_ids=f["line_ids"],
                            detail=f"Flagged by the audit rules: {f['kind'].replace('_', ' ')}.")
                for f in data["expected_flags"]
            ]
            cap = _Capture()
            logging.getLogger().addHandler(cap)
            try:
                result = app["explain_flags"](bill, app["AuditResult"](flags=flags), eob)
                letter = app["draft_dispute_letter"](bill, result, eob)
            finally:
                logging.getLogger().removeHandler(cap)
            if cap.records:  # the code-written fallback ran because Gemini failed: not a model result
                raise StopEval("Gemini failed inside the bill functions: " + cap.records[0])
            problems = []
            for f in result.flags:
                e = f.explanation
                if not all(i in e for i in f.line_ids):
                    problems.append(f"explanation for {f.line_ids} does not cite its lines")
                if "worth asking about" not in e.lower():
                    problems.append(f"explanation for {f.line_ids} lacks 'worth asking about'")
                if app["BANNED"].search(e) or re.search(r"https?://", e):
                    problems.append(f"explanation for {f.line_ids} has an accusation or a link")
                if f.detail in e:
                    problems.append(f"explanation for {f.line_ids} was replaced by the code fallback")
            if "[Your name]" not in letter or not all(i in letter for fl in flags for i in fl.line_ids):
                problems.append("letter lacks the placeholder or a flagged line")
            if app["BANNED"].search(letter):
                problems.append("letter has an accusation")
            if "What I noticed:" in letter:
                problems.append("letter fell back to the code template")
            return problems
        raise ValueError(f"unknown case type {case['type']!r}")
    except StopEval:
        raise
    except Exception as e:  # a failed API call is not a wrong answer: stop and keep progress
        raise StopEval(f"{type(e).__name__}: {str(e)[:200]}") from e


# ----------------------------------------------------------------------------- report
def report(cases, results, k):
    ids = {c["id"]: c["category"] for c in cases}
    rows = {}
    for cid, runs in results.items():
        if cid not in ids or not runs:
            continue
        for cat in (ids[cid], "ALL"):
            r = rows.setdefault(cat, {"cases": 0, "attempts": 0, "passed": 0, "full": 0, "eligible": 0})
            r["cases"] += 1
            r["attempts"] += len(runs)
            r["passed"] += sum(1 for x in runs if x["pass"])
            if len(runs) >= k:
                r["eligible"] += 1
                r["full"] += all(x["pass"] for x in runs[:k])
    lines = [f"{'category':<12}{'cases':>6}{'attempts':>10}{'pass@1':>9}{'pass^' + str(k):>16}"]
    for cat in sorted(rows, key=lambda c: (c == "ALL", c)):
        r = rows[cat]
        p1 = f"{100 * r['passed'] / r['attempts']:.1f}%"
        pk = f"{100 * r['full'] / r['eligible']:.1f}% ({r['full']}/{r['eligible']})" if r["eligible"] else "n/a"
        lines.append(f"{cat:<12}{r['cases']:>6}{r['attempts']:>10}{p1:>9}{pk:>16}")
    fails = [(cid, i + 1, x["problems"]) for cid, runs in results.items() for i, x in enumerate(runs) if not x["pass"]]
    if fails:
        lines.append("\nFailures:")
        for cid, run, probs in fails:
            lines.append(f"  {cid} (run {run}): " + "; ".join(probs))
    return "\n".join(lines)


def load_results():
    return json.load(open(RESULTS_FILE))["results"] if RESULTS_FILE.exists() else {}


def save_results(results):
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    meta = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    json.dump({"meta": meta, "results": results}, open(RESULTS_FILE, "w"), indent=2)


def load_app():
    from app import bill_explain, chat, contract, extract_terms

    return {
        "read_pages": extract_terms._read_pages,
        "extract_plan_terms": extract_terms.extract_plan_terms,
        "answer_question": chat.answer_question,
        "explain_flags": bill_explain.explain_flags,
        "draft_dispute_letter": bill_explain.draft_dispute_letter,
        "BANNED": bill_explain._BANNED,
        "NOT_FOUND_REPLY": contract.NOT_FOUND_REPLY,
        "Bill": contract.Bill, "Eob": contract.Eob, "Flag": contract.Flag, "AuditResult": contract.AuditResult,
    }


def main(argv=None, app=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args(argv)
    cases = json.load(open(CASES_FILE))
    if args.fresh and RESULTS_FILE.exists():
        RESULTS_FILE.unlink()
    results = load_results()
    if args.report:
        print(report(cases, results, args.runs))
        return 0
    selected = [c for c in cases if args.only in c["id"] or args.only in c["category"]]
    expected = json.load(open(PLANS / "expected_terms.json"))
    app = app or load_app()
    cache = {}
    try:
        for run in range(args.runs):  # run 1 for every case first, so partial results are still useful
            for case in selected:
                done = results.setdefault(case["id"], [])
                if len(done) > run:
                    continue
                t0 = time.time()
                problems = run_case(case, app, expected, cache)
                done.append({"pass": not problems, "problems": problems, "seconds": round(time.time() - t0, 1)})
                save_results(results)
                print(f"[run {run + 1}/{args.runs}] {case['id']:<22} {'PASS' if not problems else 'FAIL'}"
                      f" ({done[-1]['seconds']}s)" + ("" if not problems else "  " + "; ".join(problems)), flush=True)
    except StopEval as e:
        print(f"\nSTOPPED: {e}\nProgress is saved. Run the same command again later to resume.\n")
    print(report(cases, results, args.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
