# Figma and AI provenance reference

Use this reference before exporting any visual input. Figma is the approved
visual authority; AI generation may create a candidate raster, never an
unreviewed authority.

## Required capture

- file ID, page/frame ID, node IDs, source revision, capture timestamp;
- component names, variants, states, variables/tokens, typography and spacing;
- export format, scale, dimensions, alpha, color space, 9-slice borders,
  pivot, atlas group, naming, and intended Unity target;
- provider, model, prompt, reference-image SHA-256 list, output SHA-256,
  rights/licence status, limitations, owner, and Art Lead reviewer.

## Export contract

Export into a review-owned path, calculate SHA-256 immediately, and bind the
same hash in `ui-asset-manifest.schema.json`. Never use a private Figma URL,
credential, or unlicensed reference as a distributable artifact. Keep source
and generated candidates recoverable; do not overwrite a rejected export.

## BLOCKED conditions

Return `BLOCKED` when a Figma revision cannot be identified, export hash does
not match, rights or font ownership is unclear, AI provenance is incomplete,
the reviewer is absent, or the visual differs from approved components in an
unresolved way. A generated image preview alone is not runtime evidence.
