# Unity Offline Startup Command Reference

These commands trace startup configuration and logs read-only. They do not authorize opening or saving scenes, regenerating project files, upgrading packages, or editing serialized assets.

## Locate the offline flag source

An offline flag usually has more than one source, and the bug is normally the second one overwriting the first. Enumerate all of them before tracing.

```bash
rg -n --glob '!**/Library/**' --glob '!**/Temp/**' \
  'offline|Offline|OFFLINE|isOffline|useMockData|standalone' Assets --stats
rg -n 'offline|mock|local_server|serverUrl|apiBase' \
  Assets/StreamingAssets Assets/Resources -g '*.json' -g '*.xml' -g '*.txt' -g '*.cfg'
rg -n 'OFFLINE|MOCK|DEVELOPMENT_BUILD' ProjectSettings/ProjectSettings.asset
```

Scripting define symbols in `ProjectSettings.asset` are compile-time gates and differ per build target. A flag that is present in a config file but excluded by defines is compiled out entirely; this is not runtime precedence.

```bash
rg -n -A4 'scriptingDefineSymbols' ProjectSettings/ProjectSettings.asset
```

Do not assume a universal runtime precedence for command-line arguments, `PlayerPrefs`, `StreamingAssets`, `Resources`, or hardcoded defaults. Record every candidate source and trace the actual read/write order in project-specific code, build-target configuration, and startup logs.

```bash
rg -n 'PlayerPrefs\.(GetInt|GetString|SetInt|SetString)' Assets --glob '*.cs' | rg -i 'offline|server|mock'
rg -n 'Environment\.GetCommandLineArgs|System\.Environment\.GetCommandLineArgs' Assets --glob '*.cs'
```

## Trace bootstrap order

```bash
rg -n 'RuntimeInitializeOnLoadMethod|\[RuntimeInitializeOnLoad' Assets --glob '*.cs'
rg -n 'RuntimeInitializeLoadType\.(BeforeSceneLoad|AfterSceneLoad|BeforeSplashScreen|AfterAssembliesLoaded|SubsystemRegistration)' Assets --glob '*.cs'
rg -n 'class .*Bootstrap|class .*GameLauncher|class .*AppEntry|void Awake\(\)' Assets --glob '*.cs' | head -30
rg -n 'm_Script:' Assets/Scenes/Boot.unity | head -20
```

`RuntimeInitializeOnLoadMethod` callbacks use their declared `RuntimeInitializeLoadType`: `BeforeSceneLoad` runs before scene `Awake`, while the default `AfterSceneLoad` runs after `Awake`. Callback order within the same load type is not guaranteed. Read the explicit load type and trace the actual assignment order rather than applying a universal rule.

```bash
rg -n -A6 'm_ExecutionOrder' ProjectSettings/*.asset | head -40
```

## Read the runtime logs

Player logs, not Editor logs, are the ground truth for a built client.

```powershell
Get-Content "$env:USERPROFILE\AppData\LocalLow\<Company>\<Product>\Player.log" -Tail 300
Get-Content "$env:LOCALAPPDATA\Unity\Editor\Editor.log" -Tail 300
```

```bash
tail -n 300 ~/.config/unity3d/<Company>/<Product>/Player.log
```

Run a built client with a forced log path and offline argument, when the project supports one:

```powershell
& 'D:\Builds\MyGame\Game.exe' -logFile 'D:\Builds\MyGame\offline-run.log' -offline -screen-fullscreen 0
$exit = $LASTEXITCODE
```

Do not invent a command line switch. Confirm it exists in the argument parser first:

```bash
rg -n -B2 -A8 'GetCommandLineArgs' Assets --glob '*.cs'
```

## Separate "no network" from "handled network absence"

Offline rarely means every call is bypassed. Find the calls that still fire.

```bash
rg -n 'UnityWebRequest|HttpClient|WebSocket|TcpClient|Socket\(' Assets --glob '*.cs' | head -40
rg -n -B3 -A8 'timeout|Timeout|SetRequestHeader' Assets --glob '*.cs' | rg -n 'timeout\s*=\s*[0-9]+'
```

A default `UnityWebRequest.timeout` of `0` means no timeout, which presents as an indefinite hang rather than a fallback. That is the single most common cause of "offline mode just spins".

Confirm whether the local mock data actually exists on disk before blaming code:

```bash
rg -n 'StreamingAssets|Application\.persistentDataPath|Resources\.Load' Assets --glob '*.cs' | head -20
ls -la Assets/StreamingAssets
```

## Prove the failure is startup, not UI

```bash
rg -n 'SceneManager\.LoadScene|LoadSceneAsync|activeSceneChanged' Assets --glob '*.cs'
rg -n -A3 'm_Scenes' ProjectSettings/EditorBuildSettings.asset
```

If the expected gameplay scene never appears in the log, the fault is startup and `unity-ui-rendering-debugging` is the wrong route. State that boundary in the report.

## Evidence

Record the Unity version, entry scene, every discovered offline flag source with its precedence, the observed winner, the bootstrap execution order, the exact log path and first divergent line, the network calls that still fired with their timeout values, mock data paths and existence, the expected versus reached scene, the exact commands, and their exit codes.

Without Editor or a runnable build, live reproduction is `BLOCKED`. Report static findings as `Snapshot` and never convert them into a runtime `PASS`.
