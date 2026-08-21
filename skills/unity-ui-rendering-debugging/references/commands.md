# Unity UI Rendering Command Reference

These commands read scenes, prefabs, and logs. Do not treat them as authorization to save scenes, reimport assets, edit `.meta` files, or upgrade UI packages. Run them against an authorized working copy.

## Detect the UI stack before anything else

The three stacks answer "why is it invisible" with different fields. Detect first; do not assume uGUI.

```bash
rg -n '"com\.unity\.ugui"|"com\.unity\.ui"' Packages/manifest.json
rg -n 'mDepth:|mClipping:|mClipRange:' Assets --glob '*.prefab'
rg -n 'm_ShowMaskGraphic:|m_ClipSoftness:|m_ForceStencilTesting:' Assets --glob '*.prefab'
rg -l --glob '*.uxml' '<ui:UXML|<UXML' Assets
```

| Marker | Stack | Order field | Clipping mechanism |
|---|---|---|---|
| `com.unity.ugui` in manifest, `Canvas` in prefab | uGUI | `m_SortingOrder` / sibling index | `RectMask2D`, `Mask` |
| serialized NGUI fields (`mDepth`, `mClipping`) | NGUI | `mDepth` on panel and widget | `mClipRange` / panel clipping fields |
| `.uxml` / `.uss` assets | UI Toolkit | document sort order + DOM order | `overflow: hidden` |

## Read serialized values without opening the Editor

Unity YAML is greppable when the project uses `Force Text` serialization. Confirm that first, otherwise the results are meaningless.

```bash
rg -n 'm_SerializationMode' ProjectSettings/EditorSettings.asset
```

`m_SerializationMode: 2` means Force Text. `0` or `1` means binary or mixed, so file inspection is `BLOCKED` and you must use the Editor.

### uGUI: active state, order, and clipping

```bash
rg -n -A3 'm_IsActive:' Assets/UI/MainHud.prefab | head -40
rg -n 'm_SortingOrder:|m_OverrideSorting:|m_SortingLayerID:' Assets/UI/MainHud.prefab
rg -n 'm_ShowMaskGraphic:|m_ClipSoftness:|m_ForceStencilTesting:' Assets/UI/MainHud.prefab
rg -n -A6 'm_AnchorMin:|m_SizeDelta:|m_LocalScale:' Assets/UI/MainHud.prefab | head -60
```

`m_IsActive: 0`, `m_SizeDelta` with a zero axis, or `m_LocalScale` with a zero component each hide an object with no render-order fault at all. Check these before blaming draw order.

### NGUI: panel and widget depth

```bash
rg -n 'mDepth:|mClipping:|mClipRange:' Assets/UI/MainHud.prefab
rg -n 'mColor:|mSpriteName:|mAtlas:' Assets/UI/MainHud.prefab
```

Unity prefab YAML stores `m_Script` as a GUID reference rather than a class name, so these serialized-field scans are the static NGUI/mask hints. If the fields are absent or ambiguous, resolve the component type with the Editor API instead of guessing from `m_Script` text. NGUI resolves order as panel `mDepth` first, then widget `mDepth` inside that panel. A widget with depth 999 still renders behind a panel with a higher `mDepth`. A widget whose `mSpriteName` is absent from the bound atlas renders nothing while remaining active.

### UI Toolkit: display, opacity, and hierarchy

```bash
rg -n 'display:|visibility:|opacity:|overflow:' Assets/UI/**/*.uss
rg -n 'class=|name=' Assets/UI/MainHud.uxml | head -40
rg -n 'sortingOrder|panelSettings' Assets/UI/**/*.asset
```

## Runtime inspection when the Editor is available

Add this to an authorized editor-only script; do not commit it into gameplay assemblies.

```csharp
// uGUI: prove existence, activity, and effective visibility separately.
// Requires using System.Linq; filter by the full hierarchy path in a project-specific probe.
var go = Resources.FindObjectsOfTypeAll<Transform>()
    .FirstOrDefault(t => t.gameObject.scene.IsValid() && t.name == "Slot_03")?.gameObject;
if (go == null)
{
    Debug.Log("found=false; object is missing or inactive in the loaded scenes");
    return;
}
Debug.Log($"found={go != null} activeSelf={go?.activeSelf} activeInHierarchy={go?.activeInHierarchy}");
var g = go?.GetComponent<CanvasGroup>();
Debug.Log($"canvasGroup alpha={g?.alpha} interactable={g?.interactable} blocksRaycasts={g?.blocksRaycasts}");
var c = go?.GetComponentInParent<Canvas>();
Debug.Log($"canvas sortingOrder={c?.sortingOrder} overrideSorting={c?.overrideSorting} layer={go?.layer}");
var r = go?.GetComponent<RectTransform>();
Debug.Log($"rect sizeDelta={r?.sizeDelta} scale={r?.localScale} worldPos={r?.position}");
```

```csharp
// NGUI: read the depths that actually decide order.
// Requires using System.Linq; filter by the full hierarchy path in a project-specific probe.
var w = Resources.FindObjectsOfTypeAll<UIWidget>()
    .FirstOrDefault(x => x.gameObject.scene.IsValid() && x.name == "Slot_03");
var p = w?.panel;
Debug.Log($"widget depth={w?.depth} panelDepth={p?.depth} clipping={p?.clipping} clipRange={p?.baseClipRegion}");
```

Capture the Editor log path rather than retyping console text:

```powershell
Get-Content "$env:LOCALAPPDATA\Unity\Editor\Editor.log" -Tail 200
```

```bash
tail -n 200 ~/.config/unity3d/Editor.log
```

## Camera and layer culling

An object can be active, correctly ordered, unclipped, and still invisible because its camera excludes its layer.

```csharp
var cam = c != null && c.renderMode != RenderMode.ScreenSpaceOverlay ? c.worldCamera : Camera.main;
Debug.Log($"cullingMask={cam?.cullingMask} includesLayer={(cam != null && go != null && (cam.cullingMask & (1 << go.layer)) != 0)}");
```

For Screen Space - Overlay the camera is irrelevant; state that explicitly instead of reporting camera values as evidence.

## Diagnostic order that avoids false root causes

1. Object exists and `activeInHierarchy` is true.
2. Geometry is non-degenerate: `sizeDelta`, `localScale`, position on screen.
3. Alpha chain: `CanvasGroup.alpha`, `Image.color.a`, `mColor.a`, USS `opacity`.
4. Clipping chain: `RectMask2D`/`Mask`, `UIPanel` clip range, `overflow: hidden`.
5. Order: `sortingOrder`/sibling index, `mDepth` pair, document order.
6. Asset binding: sprite in atlas, material, shader, font.
7. Camera and layer culling.

Steps 1-3 explain most "missing UI item" reports. Reporting a draw-order cause before step 3 is a common misdiagnosis.

## Evidence

Record the hierarchy path, serialization mode, detected stack, `activeInHierarchy`, the measured geometry and alpha values, the clipping chain, the order values for both levels, sprite/atlas/material names, camera culling mask, the exact commands, and the Unity version.

A screenshot is not evidence of render order. Values are. Without Editor access, live confirmation is `BLOCKED`; report the serialized findings as `Snapshot` and do not upgrade them to a runtime `PASS`.
