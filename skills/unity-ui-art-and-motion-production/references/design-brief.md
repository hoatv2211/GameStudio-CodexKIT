# UI design brief and prompt contract

Use this reference before asking an image model for a new UI visual or a visual
variant. Treat the brief as a compact style system, not a prose mood board.

## Required brief shape

Record these sections in `ui-design-brief.json`:

```text
GOAL              screen, audience, success criteria
FORMAT            width, height, scale, safe margins
LAYOUT            grid and hierarchy
TYPE SYSTEM       font family, weights, leading, tracking
COLOR + MATERIAL  background, text, accent, texture
IMAGERY           style lane, references, material language
COPY              exact lines and text policy
CONSTRAINTS       must keep, change only, negative constraints
VARIANTS          one controlled change per candidate
```

Keep copy empty when the image model is only generating a frame or icon. If
copy is required, default to `typeset-in-figma`; do not accept AI-rendered UI
text as final localization or typography evidence.

## Prompt and variant rules

- Make the reference visible before asking an image tool to preserve identity,
  palette, material, or layout rhythm.
- Lock the first approved system, then change one visual variable at a time:
  texture intensity, accent, crop, or card arrangement.
- Keep negative constraints explicit: no watermark, no extra text, no invented
  logos, no unapproved gradients, no altered safe area, no extra controls.
- Use a clean text-safe area and typeset in Figma when typography matters.
- Store prompt text, reference hashes, output hash, variant ID, reviewer, and
  Figma revision in the asset evidence; never rely on model memory of a style.

## Static QC

Run `scripts/ui_art_qc.py` after export. It checks brief/schema closure, source
revision parity, PNG dimensions, alpha expectation, variant IDs, and text policy.
It does not prove visual approval, rights, atlas quality, or Unity runtime
behavior; those remain separate evidence gates.
