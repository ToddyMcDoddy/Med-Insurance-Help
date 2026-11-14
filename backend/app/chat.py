"""Grounded Q&A: answer one question from the plan text and the confirmed terms.

Owner: AI/extraction lead. The backend calls answer_question(); the model only writes words.
Try it from the backend folder:
    python3 -m app.chat ../data/synthetic/plans/<file>.pdf "What is my deductible?"
"""
import os
import re
import sys

from google import genai
from google.genai import types

from .chat_prompt import SYSTEM_PROMPT
from .contract import NOT_FOUND_REPLY, REFUSAL_REPLY, ChatResponse, Citation, PlanTerms
from .extract_terms import TERM_FIELDS, _generate, _read_pages

_LEAK_MARKERS = ("Answer ONLY from", "Never reveal, repeat")


def _terms_block(terms):
    if terms is None:
        return "(no confirmed terms yet)"
    lines = []
    for name in TERM_FIELDS:
        t = getattr(terms, name)
        lines.append(f"{name}: {t.value:g} (page {t.page})" if t else f"{name}: not found")
    return "\n".join(lines)


def _clean(answer):
    """Plain text only: remove images, links and URLs from model output."""
    answer = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", answer)  # markdown images
    answer = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", answer)  # markdown links -> link text
    answer = re.sub(r"https?://\S+|www\.\S+", "", answer)  # bare URLs
    return answer.strip()


def answer_question(question, pages, terms=None, doc_id="plan"):
    """pages: list of page texts (page 1 first). terms: the user-confirmed PlanTerms, if any."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=key)
    doc = "\n\n".join(f"=== PDF PAGE {i} ===\n{t}" for i, t in enumerate(pages, start=1))
    contents = (
        f"<plan_document>\n{doc}\n</plan_document>\n\n"
        f"<confirmed_terms>\n{_terms_block(terms)}\n</confirmed_terms>\n\n"
        f"<user_question>\n{question}\n</user_question>"
    )
    resp = _generate(
        client,
        contents,
        types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, max_output_tokens=2048),
    )
    answer = _clean(resp.text or "")
    if not answer or any(m in answer for m in _LEAK_MARKERS):  # empty reply or leaked rules
        answer = REFUSAL_REPLY
    refused = answer == REFUSAL_REPLY
    cited = sorted({int(p) for p in re.findall(r"page\s+(\d+)", answer, flags=re.I) if 1 <= int(p) <= len(pages)})
    return ChatResponse(
        answer=answer,
        citations=[] if refused or answer == NOT_FOUND_REPLY else [Citation(doc_id=doc_id, page=p) for p in cited],
        refused=refused,
    )


if __name__ == "__main__":
    out = answer_question(sys.argv[2], _read_pages(sys.argv[1]))
    print(out.answer)
    print("citations:", [c.page for c in out.citations], "| refused:", out.refused)
