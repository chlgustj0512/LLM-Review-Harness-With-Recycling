# Analogy Review Harness

논증 오류 특화 적대 평가와 목적-주석 기반 실패 재활용을 결합한 다측면 LLM 심사 하네스

**English title:** A Multi-Aspect LLM Review Harness for Adversarial Argument-Error Evaluation and Purpose-Annotated Failure Recycling

Author: **Hyunseo Choi (최현서)**  
ORCID: [0009-0002-7757-0274](https://orcid.org/0009-0002-7757-0274)  
Current release: **v0.15.1**

Zenodo DOI: [10.5281/zenodo.20814616](https://doi.org/10.5281/zenodo.20814616)  
Repository: [chlgustj0512/LLM-Review-Harness-With-Recycling](https://github.com/chlgustj0512/LLM-Review-Harness-With-Recycling)

## What this project is

This repository contains a research prototype for reviewing LLM-generated claims through multiple aspect-specific reviewers instead of compressing every concern into one score.

The implemented pipeline connects:

```text
Task
  -> candidate generation
  -> sequential multi-aspect review
  -> Event Contract validation
  -> explicit human Gate decisions
  -> appeal and case confirmation
  -> confirmed-failure feedback
  -> purpose-annotated salvage library
  -> ratchet and termination snapshot
  -> non-blocking post-review audit
  -> final delivery packet
```

The restricted adversarial generator creates labeled argument-error test cases. It does not generate system attacks, permission bypasses, tool-execution attacks, memory manipulation, social engineering, or security-exploitation content.

## Research claim boundary

The software architecture is implemented and regression-tested. The following remains a research hypothesis:

> Under matched evaluation conditions, the harness may achieve **better evaluation performance** than Single LLM-as-Judge, PoLL, Self-Refine, Reflexion, N-Critics, and Multi-Agent Debate for argument-error detection and confirmed-failure reuse.

“Better evaluation performance” means measurable improvement in predefined outcomes such as:

- argument-error detection recall;
- clean-case false rejection;
- defect-type and location accuracy;
- recurrence after confirmed feedback;
- provenance and state-transition violations;
- cost and latency as secondary outcomes.

No general claim that the system is better in every respect is made.

## Current verification state

As of 2026-06-23:

- package version: `0.15.1`;
- automated regression tests: **133/133 passed**;
- Python `compileall`: passed;
- default probe set: 20 cases;
- local-model probe run:
  - flawed cases detected: **14/14**;
  - clean cases correctly passed: **4/6**;
  - strict contract score: **17/20**;
  - observed false positives: `clean-code-001`, `clean-physics-001`;
  - unresolved jurisdiction case: `clean-scope-001` returned `empty_aspect`.

The strict score treats a clean case as correct only when the required aspect is actually reviewed and the batch ends in `clear`. A missing required aspect is not counted as a successful pass.

## Implemented components

- Sequential reviewer registry with self-declared jurisdiction.
- Structured review contracts.
- Common Event Contract Validator across Gate, Case, Library, Ratchet, Snapshot, and delivery events.
- Three-stage human-controlled Gate state machine.
- External appeal packet and result binding.
- Confirmed/dismissed case lifecycle.
- Explicit readiness and activation before negative-example feedback.
- Purpose-annotated salvage library.
- Aspect-priority ratchet and immutable champion snapshot.
- Restricted argument-defect test-case generator with Hidden Oracle separation.
- Non-blocking OLMo 2 post-review audit.
- Final delivery packet export in JSON and Markdown.

## Not implemented or not yet demonstrated

- Automatic 10-axis 0-100 rubric and 60/75/85 Gate thresholds.
- A completed large-scale comparison against the six planned baselines.
- A demonstrated general cross-domain analogy-performance gain.
- Fully independent model lineages for every role.
- A validated replacement for human Gate decisions.

## Installation

Requirements:

- Python 3.11 or later;
- Ollama for local-model execution;
- installed local models when using the `ollama` backend.

```powershell
python -m pip install -e .
python -m unittest discover -s tests
```

## Quick start

Deterministic mock run:

```powershell
python -m harness run --backend mock --task "검토할 주장을 작성하라"
python -m harness probe --backend mock
```

Local model profile:

```powershell
python -m harness probe --backend ollama --model-profile confirmed-local
```

On Windows PowerShell, preserve the final JSON bytes with:

```powershell
cmd /c "python -m harness probe --backend ollama --model-profile confirmed-local > result.json"
```

## Repository map

```text
harness/                  implementation
tests/                    automated regression tests
MODEL_ROSTER.md           confirmed local role-model mapping
OPERATIONS.md             operating procedures
PATCH_NOTES.md            version history
docs/SYSTEM_DESIGN.pdf    Zenodo-ready design disclosure
docs/PROBE_20_REPORT.md   current local-model probe interpretation
CITATION.cff              citation metadata
.zenodo.json              Zenodo metadata draft
```

## Citation

Use the repository’s `CITATION.cff` or cite the reserved Zenodo DOI:

> Choi, Hyunseo. (2026). *A Multi-Aspect LLM Review Harness for Adversarial Argument-Error Evaluation and Purpose-Annotated Failure Recycling* (Version 0.15.1) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.20814616

## Licenses

- Software source code: [Apache License 2.0](LICENSE)
- Documentation and system-design PDF: [CC BY 4.0](LICENSE-DOCUMENTATION.md)

Zenodo supports mixed-license uploads. Add both `Apache-2.0` and `CC-BY-4.0` in the record’s Licenses field.

## Patent and disclosure notice

GitHub and Zenodo publication can provide dated public-disclosure evidence and may function as defensive publication. It is not a patent filing and does not create universal patent priority. If patent protection may matter, obtain qualified legal advice before publication.
