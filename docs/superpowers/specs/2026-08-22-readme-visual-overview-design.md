# README Visual Overview Design

## Goal

Break up the lean README with the existing handcrafted showcase while keeping
the page concise, accessible, and useful to search engines.

## Approved layout

- Place `## Visual overview` between `## Why MOStudio Kit` and
  `## What you can do`.
- Display `slide-01.webp` at full width as the visual summary.
- Display `slide-02.webp` through `slide-07.webp` in three two-column rows.
- Keep all seven images visible; do not use a collapsed `<details>` block.
- Omit `slide-08.webp` because the nearby Install section already owns that
  information.
- Reuse the existing assets without regeneration or image edits.

## Content and accessibility

Each image receives unique descriptive alt text that communicates the subject,
not the decorative style. Each pair receives a short text caption so the page
does not rely on text baked into an image for meaning or indexing.

## Verification

The README contract must find exactly `slide-01.webp` through
`slide-07.webp`, must not find `slide-08.webp`, and must keep the total README
word count below 1,600. Packaging, documentation, validation, secret, policy,
routing, collision, doctor, and full unittest gates remain required.
