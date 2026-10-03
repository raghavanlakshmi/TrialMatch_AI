# Criterion evaluation

Labels: 29 criteria from SYN-001 demo trials. Reviewed By Lakshmi on 10/3/26.

| Method | Accuracy | Decidable correct | Unsafe false clearance | UNKNOWN to MEETS | False exclusion |
|---|---|---|---|---|---|
| rule_baseline | 0.83 | 0.58 (12) | 0 | 0 | 0 |
| llm_assessor | 0.86 | 0.92 (12) | 3 | 3 | 1 |

## Mismatches

- rule_baseline · NCT06412198 INC-01: expected MEETS, got UNKNOWN
- rule_baseline · NCT06412198 INC-03: expected MEETS, got UNKNOWN
- rule_baseline · NCT06412198 INC-13: expected MEETS, got UNKNOWN
- rule_baseline · NCT07559760 INC-01: expected MEETS, got UNKNOWN
- rule_baseline · NCT07559760 EXC-01: expected MEETS, got UNKNOWN (judgment call)
- llm_assessor · NCT06252649 INC-02: expected UNKNOWN, got MEETS
- llm_assessor · NCT07559760 INC-03: expected UNKNOWN, got MEETS
- llm_assessor · NCT07559760 INC-10: expected UNKNOWN, got MEETS
- llm_assessor · NCT07559760 EXC-01: expected MEETS, got DOES_NOT_MEET (judgment call)
