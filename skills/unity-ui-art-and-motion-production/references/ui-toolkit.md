# Unity UI Toolkit reference

## Detection markers

- `Assets/**/*.uxml`; or
- `Assets/**/*.uss`.

## Owned Unity artifact types

UXML documents, USS stylesheets, UI Builder component assets, PanelSettings,
style variables, vector/raster assets, and project controllers for stateful
motion.

## Allowed native motion drivers

USS transitions or an existing project controller. External tween packages are
not installed; existing DOTween/LeanTween evidence must be explicit if a
project controller wraps one.

## Import settings and static verification

Check UXML/USS references, style-sheet order, variables/tokens, panel scale
mode, atlas/vector import, font fallback, picking mode, focus order, and
serialized asset paths. Validate no unsafe or duplicate target path and no
unreviewed generated stylesheet.

## Runtime scenarios and performance evidence

Exercise responsive breakpoints, keyboard/gamepad focus, pointer states,
localization expansion, popup interruption, reduced-motion mode, and panel
rebuild behavior. Capture frame-time/allocation samples, UI debugger notes,
screenshots/video, Unity version, target tier, and sample count.

## Restore evidence

Keep before/after hashes for UXML/USS and PanelSettings, a backup manifest, and
a tested restore command. A visual match without serialized-reference and
restore evidence is BLOCKED.
