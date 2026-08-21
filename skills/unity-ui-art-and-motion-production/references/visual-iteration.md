# Visual iteration and art QC

Use this reference when a generated candidate is close but not yet approved.

## Iteration loop

1. Freeze the accepted Figma/style brief and identify one defect.
2. Change one or two declared variables only; keep layout, identity, safe area,
   and material language fixed.
3. Generate a candidate, retain the raw source, and record its variant ID and
   prompt hash.
4. Run static QC, then inspect a contact sheet or preview at full and reduced
   size.
5. Approve, reject, or return for another bounded variant. Never silently
   overwrite the accepted export.

## Art checks

- dimensions and pixel density match the manifest;
- PNG, JPEG, and SVG payloads are structurally valid for the declared format;
- the exported SHA-256 matches the asset manifest and AI output provenance;
- alpha is clean around silhouettes and does not halo into the UI background;
- 9-slice corners remain intact and borders are documented;
- atlas grouping, pivot, scale, and color space remain unchanged unless the
  brief explicitly authorizes the change;
- text is absent from generated raster art when Figma typesetting is required;
- no watermark, invented logo, extra control, or unexplained style drift;
- the asset remains legible at target and reduced preview sizes.

## Evidence boundary

Static QC is `Verified` only for the checks it actually performs. SVG alpha is
reported as not pixel-decoded; Figma review, Unity import, device layout, motion
interruption, reduced-motion behavior, and performance still require their own
evidence. Missing tool or runtime evidence is `BLOCKED`, never a visual-quality
PASS.
