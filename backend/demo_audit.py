"""Run the deterministic medical-bill audit against synthetic demo cases."""

import json
from pathlib import Path

from app.audit import audit
from app.contract import Bill, Eob


ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "data" / "synthetic" / "bills"


def main():
    print("=" * 65)
    print("MEDIFIT — MEDICAL BILL AUDIT DEMO")
    print("=" * 65)
    print("Synthetic examples only. Not medical, legal, or financial advice.")

    for path in sorted(SAMPLE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))

        bill = Bill.model_validate(data["bill"])
        eob = (
            Eob.model_validate(data["eob"])
            if data.get("eob")
            else None
        )

        result = audit(bill, eob)

        print(f"\n{'-' * 65}")
        print(f"Example: {path.name}")
        print(f"Bill ID: {bill.bill_id}")
        print(f"Description: {data.get('description', '')}")
        print(f"Items reviewed: {len(bill.items)}")
        print(f"Flags found: {len(result.flags)}")

        if not result.flags:
            print("Result: No issues flagged.")
        else:
            for flag in result.flags:
                print(f"\n  Issue: {flag.kind}")
                print(f"  Affected lines: {', '.join(flag.line_ids)}")
                print(f"  Details: {flag.detail}")

        print(f"\n  {result.disclaimer}")

    print(f"\n{'=' * 65}")
    print("DEMO COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
