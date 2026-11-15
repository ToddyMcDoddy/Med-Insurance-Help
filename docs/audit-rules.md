# Medical bill audit rules

The deterministic auditor compares bill line items with one another and, when
provided, with matching Explanation of Benefits (EOB) lines. A flag means
**“worth asking about”**; it is not an accusation and does not establish that
an error occurred.

## Matching fields

- Provider names are compared case-insensitively after trimming and collapsing
  whitespace.
- Service dates and procedure codes must match exactly.
- Dollar amounts are compared to the nearest cent.

## Flags

| Flag | Rule |
|---|---|
| `exact_duplicate` | Same provider, date of service, procedure code, and amount appear on two or more bill lines. Three or more identical lines are grouped into one flag containing every involved `line_id`. |
| `near_duplicate` | Same provider, date of service, and procedure code appear with different amounts. |
| `same_service_twice` | Same procedure code and date appear under different providers. |
| `eob_mismatch` | A matching bill line is not above the EOB allowed amount, but its billed amount differs from the EOB member-owes amount. |
| `balance_billing` | A matching bill line is greater than the EOB allowed amount. |

EOB matching uses provider, date of service, and procedure code. If no matching
EOB line exists, no EOB comparison flag is emitted for that bill line.

Different procedure codes on the same date are not, by themselves, a duplicate
or repeated-service finding.

## Output and wording

Each flag contains its kind, the relevant bill `line_ids`, and a deterministic
factual `detail` sentence. Wording must say the item is **“worth asking about”**
and must never characterize a bill or provider as committing fraud.
