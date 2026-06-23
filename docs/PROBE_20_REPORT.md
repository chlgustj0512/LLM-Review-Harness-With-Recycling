# Local-model 20-probe report

Run date: 2026-06-23  
Software version at analysis: 0.15.1  
Backend: Ollama  
Profile: `confirmed-local`

## Outcome

| Category | Result |
|---|---:|
| Flawed cases detected | 14 / 14 |
| Clean cases returned without a defect | 4 / 6 |
| Clean cases satisfying the strict `clear` contract | 3 / 6 |
| Strict total | 17 / 20 |

The strict total counts a clean case as correct only when:

1. no reviewer reports a defect; and
2. the required aspect is actually reviewed; and
3. the batch status is `clear`.

## Cases requiring follow-up

### `clean-code-001`

- Expected: clear.
- Observed: defect reported by `math_reviewer`.
- Classification: False Positive(거짓 양성).
- Follow-up: inspect whether the math reviewer invents a numerical or type requirement not present in the candidate.

### `clean-physics-001`

- Expected: clear.
- Observed: defect reported by `physics_reviewer`.
- Classification: False Positive(거짓 양성).
- Follow-up: inspect parsing of `v^2`, Unicode multiplication marks, and dimensional notation.

### `clean-scope-001`

- Expected: clear after scope review.
- Observed: no defect, but batch status `empty_aspect`.
- Classification: unresolved jurisdiction, not a successful pass.
- Follow-up: strengthen scope-jurisdiction recognition for qualified generalization language without making the reviewer applicable to every abstract claim.

## Interpretation

The result supports a narrow statement:

> In this 20-case local run, the model panel detected all 14 inserted flawed cases but did not yet preserve all clean controls.

It does not establish better evaluation performance than other methods. That requires matched baselines, hidden labels, repeated runs, and statistical analysis.

## Source integrity note

The original `result.json` produced through PowerShell `Out-File` contains malformed string content and is not treated as the authoritative machine-readable artifact. This report was reconstructed from the append-only `runs/events.jsonl` probe events.

