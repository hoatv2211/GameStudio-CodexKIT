# Unity uGUI reference

## Detection markers

- `Packages/manifest.json` contains `com.unity.ugui`; or
- a bounded UTF-8 `.prefab` contains `Canvas`.

## Owned Unity artifact types

Canvas/panel/prefab, Image/RawImage/Sprite assets, SpriteAtlas, 9-slice
border metadata, Animator Controller/AnimationClip, and UI-specific materials.

## Allowed native motion drivers

Animator, AnimationClip, or an existing project controller. An external
DOTween/LeanTween driver requires evidence of an already-installed dependency;
never install it from this workflow.

## Import settings and static verification

Check texture type Sprite (2D and UI), alpha, sRGB, pixels-per-unit, pivot,
border, atlas membership, compression, Canvas render mode, anchors, raycast
targets, Animator transitions, exit times, and serialized references. Confirm
GUID/meta stability and no duplicate target path before applying.

## Runtime scenarios and performance evidence

Exercise show/hide, interrupt/reverse, resolution/aspect changes, keyboard or
controller navigation, localization expansion, and reduced-motion mode. Capture
frame-time/allocation samples on the target tier and record screenshot/video,
Unity version, scene, sample count, and limits.

## Restore evidence

Keep the before hash, backup manifest, target list, and a tested restore command.
An applied uGUI result without these artifacts is not a PASS.
