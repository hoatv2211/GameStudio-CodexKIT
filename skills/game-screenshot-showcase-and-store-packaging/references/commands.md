# Game Screenshot Showcase Command Reference

Use approved project paths only. These commands capture or package evidence without uploading, signing, or submitting anything.

## Unity Editor capture

```powershell
$unityExe = 'C:\Program Files\Unity\Hub\Editor\2021.3.45f1\Editor\Unity.exe'
$projectRoot = 'D:\Projects\MyGame'
$logPath = 'D:\Evidence\ScreenshotShowcase\Editor.log'

& $unityExe -batchmode -nographics -quit `
  -projectPath $projectRoot `
  -executeMethod Studio.ScreenshotShowcase.CaptureApproved `
  -captureMode Editor `
  -logFile $logPath
$editorExitCode = $LASTEXITCODE
```

## Unity PlayMode capture

```powershell
$unityExe = 'C:\Program Files\Unity\Hub\Editor\2021.3.45f1\Editor\Unity.exe'
$projectRoot = 'D:\Projects\MyGame'
$logPath = 'D:\Evidence\ScreenshotShowcase\PlayMode.log'

& $unityExe -batchmode -nographics -quit `
  -projectPath $projectRoot `
  -executeMethod Studio.ScreenshotShowcase.CaptureApproved `
  -captureMode PlayMode `
  -logFile $logPath
$playModeExitCode = $LASTEXITCODE
```

## Helper CLI

```powershell
python -B scripts/screenshot_showcase.py verify-capture D:\Projects\MyGame --record D:\Evidence\capture-record.json
python -B scripts/screenshot_showcase.py contact-sheet --records D:\Evidence\records.json --output D:\Evidence\review.html
python -B scripts/screenshot_showcase.py export-manifest --deck D:\Evidence\showcase-deck.json --platform steam --locale en-US --output-root D:\Evidence\Steam
```

```bash
python -B scripts/screenshot_showcase.py verify-capture /srv/my-game --record /srv/evidence/capture-record.json
python -B scripts/screenshot_showcase.py contact-sheet --records /srv/evidence/records.json --output /srv/evidence/review.html
python -B scripts/screenshot_showcase.py export-manifest --deck /srv/evidence/showcase-deck.json --platform steam --locale en-US --output-root /srv/evidence/steam
```

## Evidence

Record the exact command, approved plan ID, Unity version, project root, scene or flow, capture mode, locale, device or viewport, output root, raw file path, hash, byte size, dimensions, reviewer, approval state, runtime verdict, visual verdict, store verdict, and limitations.

## Mutation boundaries

Do not overwrite raw captures, delete rejected evidence, traverse outside approved roots, upload assets, sign binaries, accept store legal screens, or submit to storefronts. Report-only packaging may create new evidence files, manifests, and review artifacts only within the approved output roots.
