# Criterion evaluation (held-out)

Labels: 21 criteria (criterion_labels_heldout.json). Reviewed by Lakshmi on 10/3/26; EXC-04 and NCT07281716 INC-01 marked as judgment calls (MSS used as proxy for pMMR).

| Method | Accuracy | Decidable correct | Unsafe false clearance | UNKNOWN to MEETS | False exclusion |
|---|---|---|---|---|---|
| rule_baseline | 0.62 | 0.20 (10) | 0 | 0 | 0 |
| llm_assessor | 0.90 | 0.90 (10) | 1 | 1 | 0 |

## Mismatches

- rule_baseline · NCT05854498 INC-01: expected MEETS, got UNKNOWN
- rule_baseline · NCT05854498 INC-03: expected MEETS, got UNKNOWN
- rule_baseline · NCT05854498 INC-04: expected MEETS, got UNKNOWN (judgment call)
- rule_baseline · NCT05854498 INC-05: expected MEETS, got UNKNOWN
- rule_baseline · NCT05854498 EXC-02: expected MEETS, got UNKNOWN
- rule_baseline · NCT05854498 EXC-04: expected MEETS, got UNKNOWN (judgment call)
- rule_baseline · NCT06244771 INC-01: expected MEETS, got UNKNOWN
- rule_baseline · NCT07281716 INC-01: expected MEETS, got UNKNOWN (judgment call)
- llm_assessor · NCT05854498 EXC-02: expected MEETS, got UNKNOWN
- llm_assessor · NCT06244771 INC-04: expected UNKNOWN, got MEETS
