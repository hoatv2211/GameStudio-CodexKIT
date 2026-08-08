# Unity Batchmode Command Reference

Use project-owned build methods and explicit paths. Replace placeholders only after inspecting the target project.

## Windows PowerShell

```powershell
$unityExe = 'C:\Program Files\Unity\Hub\Editor\2021.3.45f1\Editor\Unity.exe'
$projectPath = 'D:\Projects\MyGame'
$buildPath = 'D:\Builds\MyGame\Game.exe'
$logPath = 'D:\Builds\MyGame\Editor.log'

& $unityExe -batchmode -nographics -quit `
  -projectPath $projectPath `
  -executeMethod Studio.Build.PerformWindows64 `
  -buildTarget StandaloneWindows64 `
  -buildPath $buildPath `
  -logFile $logPath
$buildExitCode = $LASTEXITCODE
```

## Linux or macOS shell

```bash
"$UNITY_EXE" -batchmode -nographics -quit \
  -projectPath "$PROJECT_PATH" \
  -executeMethod Studio.Build.PerformLinux64 \
  -buildTarget StandaloneLinux64 \
  -buildPath "$BUILD_PATH" \
  -logFile "$LOG_PATH"
build_exit_code=$?
```

## Artifact inspection

```powershell
Get-Item -LiteralPath $buildPath | Select-Object FullName,Length,LastWriteTimeUtc
Get-FileHash -LiteralPath $buildPath -Algorithm SHA256
Select-String -LiteralPath $logPath -Pattern 'error CS|BuildFailedException|Aborting batchmode|License'
```

```bash
test -e "$BUILD_PATH"
sha256sum "$BUILD_PATH"
rg -n "error CS|BuildFailedException|Aborting batchmode|License" "$LOG_PATH"
```

## Evidence

Record the exact command, Unity version, project snapshot, exit code, Editor.log path, artifact path, size, hash, duration, and known side effects.

Do not treat exit code zero as PASS when the expected artifact is absent. Do not add package upgrades, scene saves, project-setting edits, or release-output overwrites to a diagnostic build without approved scope.
