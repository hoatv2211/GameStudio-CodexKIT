# Studio Context Brief Commands

These commands generate derived projections from one trusted local Goal. They do not authorize transcript ingestion, source mutation, Goal control, handoff replacement, or paths outside the selected goal root.

## Generate projections

From a full kit clone:

```powershell
python -B -m scripts.context_brief --goal-root <goal-root> --projection all --json
```

From a standalone installed skill directory:

```powershell
python -B scripts/context_brief.py --goal-root <goal-root> --projection all --json
```

Use `brief`, `working`, or `resume` instead of `all` for one projection. Inputs are `<goal-root>/goal.json` and `<goal-root>/state.json`; arbitrary transcript text is not an accepted input.

## Interpret output

Each JSON artifact must include `projection`, `status`, `count_kind`, `count`, `target`, `hard_cap`, `text`, `required_fact_refs`, and `evidence_label`.

- `exact_tokenizer` means the supported runtime tokenizer measured the text.
- `utf8_byte_fallback` means only conservative byte-bounded output was measured; exact runtime token count stays `Unverified`.
- `READY` requires non-empty text within the cap.
- `BLOCKED` requires empty `text`, retained `required_fact_refs`, and `evidence_label: BLOCKED`; together those fields mean the projection is not standalone context.

Targets and hard caps are `brief` 150/300, `working` 800/1,200, and `resume` 1,600/2,400. Never edit artifacts to bypass these values.

## Diagnostic order

1. Validate exact goal root and trusted `goal.json` plus `state.json`.
2. Check safety, ownership, negations, and blockers first.
3. Check current packet, exact next action, paths, commands, symbols, numbers, units, decisive errors, artifacts, and evidence labels.
4. Check measurement kind before interpreting count.
5. Check `status`, `text`, `required_fact_refs`, and `evidence_label` before consuming text.
6. For durable transfer, run `studio-handoff` and refresh repository evidence.

This order prevents compact text from hiding a missing required fact or being mistaken for an authoritative handoff.

## Evidence

Record the canonical projection's goal ID, kind, status, measurement kind/count, target, hard cap, text, required fact references, and evidence label. Interpret `BLOCKED` plus empty text as not standalone-safe. Outside the projection JSON, keep `studio-handoff` as durable authority. Missing structured sources, invalid state, overflow, or a requested boundary violation is `BLOCKED`, never `PASS`.
