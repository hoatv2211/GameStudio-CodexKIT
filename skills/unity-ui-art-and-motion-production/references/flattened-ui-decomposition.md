# Flattened UI screenshot decomposition

Use this reference when the source is one flattened or AI-generated UI image
and the team must decide what becomes Unity art, a native UI node, or a
background restoration input. This is a report-only design contract; it does
not authorize image-model calls, Figma writes, Unity mutation, or runtime PASS.

## Authority and provenance

- Hash the source image before analysis and record its original pixel width and
  height. Every bbox stays in that source coordinate space; never normalize to
  a guessed device size or percentage.
- AI detection is a candidate list. A human must move, resize, accept, reject,
  or split each bbox before it can enter the Unity asset manifest.
- Keep the source image and rejected candidates recoverable. A confidence score
  or generated preview is not visual approval, licensing evidence, or runtime
  evidence.

## Classification contract

Use `raster` for visual detail that cannot be rebuilt reliably as ordinary text,
simple CSS/vector geometry, or a Unity-native control. Use `native-ui` for
ordinary text, buttons, cards, tabs, navigation, form controls, and simple
layout. Use `background` for a continuous illustrated, photographic, textured,
or branded region that should remain a single backdrop. Use `discard` only for
an explicitly rejected candidate.

Artistic lettering, campaign marks, and integrated branding remain baked into a
background or raster asset unless the reviewer explicitly separates them.

## Background restoration contract

For each covered background, record `baked_visuals` and overlays. A
`code-overlay` is a control or ordinary UI element to remove before repair; a
`raster-overlay` is an independent bitmap that remains a foreground asset.
Every overlay bbox must intersect its parent background bbox and must be
reviewed independently.

Retain at least two hash-bound restoration variants when repair is requested:
`raw-full` (the model's full result) and `local-composite` (only the selected
region composited back over the original). The original is never overwritten;
the reviewer selects the variant that becomes the approved background.

## Unity handoff

After review, map accepted candidates to Figma node IDs and the Unity target.
Run the normal asset preflight for format, alpha, scale, pivot, 9-slice borders,
atlas group, compression, and path containment. A decomposition manifest can
prepare an import plan, but only the Figma-bound asset manifest and later Unity
evidence can establish production authority.
