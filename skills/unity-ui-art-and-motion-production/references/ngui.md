# NGUI reference

## Detection markers

- `Assets/NGUI` or another `Assets/**/NGUI` directory; or
- a bounded UTF-8 `.prefab` contains `UIPanel`.

## Owned Unity artifact types

UIAtlas/sprites, UIWidget/UITexture/UILabel-related presentation assets,
UIPanel/popup prefabs, AnimationClip, and existing NGUI TweenAlpha/TweenScale/
TweenPosition components.

## Allowed native motion drivers

Existing NGUI tween components or AnimationClip, plus an existing project
controller. DOTween/LeanTween requires explicit existing dependency evidence and
is never installed.

## Import settings and static verification

Check atlas material and padding, sprite borders, pixel dimensions, panel depth,
widget pivots, anchors, clipping, collider/raycast settings, tween duration and
ease, and serialized atlas/component references. Do not bulk reimport the atlas.

## Runtime scenarios and performance evidence

Exercise popup open/close, interruption, panel clipping, depth ordering, touch
and keyboard input, long labels, device resolutions, and reduced-motion mode.
Capture frame-time, allocations, draw-call/atlas observations, screenshots or
video, Unity/NGUI versions, and sample count.

## Restore evidence

Record the original prefab/atlas hashes, backup root, exact changed files, and a
restore command. Missing restore evidence remains BLOCKED.
