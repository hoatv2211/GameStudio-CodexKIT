# Verification Command Reference

These commands produce reproducible verdicts. A command that starts services, imports data, writes caches outside build output, or opens an editor is not read-only; route it through the relevant safety workflow before running it.

## Capture exit codes correctly

The exit code is the primary evidence field, and it is the one most often lost by piping.

```bash
python -B -m unittest discover -s tests -p "test_*.py"
exit_code=$?
echo "exit=$exit_code"
```

```bash
# Wrong: $? is tail's status, not the test runner's.
pytest -q | tail -5; echo $?
# Right:
set -o pipefail
pytest -q | tail -5
echo "exit=${PIPESTATUS[0]}"
```

```powershell
& dotnet test .\Server.sln --nologo
$exitCode = $LASTEXITCODE
Write-Output "exit=$exitCode"
```

`$LASTEXITCODE` applies to native executables. For PowerShell cmdlets use `$?`, which is a boolean and is not an exit code. Do not report one as the other.

## Snapshot the environment without changing it

```bash
python --version
git rev-parse HEAD
git status --porcelain | wc -l
uname -a
```

```powershell
$PSVersionTable.PSVersion
(Get-Command python).Source
git rev-parse HEAD
```

A dirty worktree changes what the evidence means. Record the modified-file count alongside the commit; a `PASS` on a dirty tree is `Snapshot`, not a reproducible `Verified` claim about that commit.

## Narrow the check before widening it

Run the smallest command that can prove the claim, then widen only if it passes.

```bash
python -B -m unittest tests.packaging.test_codex_plugin -v
python -B -m unittest discover -s tests -p "test_*.py"
```

```bash
pytest tests/test_inventory.py::test_stack_limit -q
pytest tests/ -q
```

```bash
dotnet build ./Server.sln -c Release --nologo -v minimal
dotnet test ./Server.sln --filter FullyQualifiedName~Inventory --nologo
```

```bash
cmake --build build --target game-server -j 8 2>&1 | tee build.log
echo "exit=${PIPESTATUS[0]}"
```

A full-suite pass after a targeted failure is not proof the targeted case was fixed. Re-run the narrow command and record both.

## Inspect the artifact, not only the exit code

Exit code zero with a missing or stale artifact is still `FAIL`.

```bash
ls -la build/game-server
stat -c '%n %s %y' build/game-server
sha256sum build/game-server
```

```powershell
Get-Item 'D:\Builds\MyGame\Game.exe' | Select-Object FullName,Length,LastWriteTime
Get-FileHash 'D:\Builds\MyGame\Game.exe' -Algorithm SHA256
```

Compare `LastWriteTime` against the moment the command started. An artifact older than the run means the build was skipped or cached, and the verdict must say so.

## Prove freshness

```bash
start_epoch=$(date +%s)
python -B -m unittest discover -s tests -p "test_*.py"
exit_code=$?
artifact_epoch=$(stat -c %Y build/report.json 2>/dev/null || echo 0)
echo "fresh=$([ "$artifact_epoch" -ge "$start_epoch" ] && echo yes || echo no) exit=$exit_code"
```

Previously captured output is never fresh evidence. If the run cannot be repeated now, the correct label is `Snapshot`.

## Runtime smoke checks beyond compilation

Compile success proves the code parses, nothing more. A runtime claim needs a runtime signal.

```bash
./build/game-server --selftest; echo "exit=$?"
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/healthz
```

```bash
timeout 30 ./build/game-server --dry-run 2>&1 | tee runtime.log
echo "exit=${PIPESTATUS[0]}"
rg -n 'FATAL|Unhandled|Assertion failed' runtime.log
```

A clean exit code with `FATAL` lines in the log is a `FAIL`. Grep the log rather than trusting the status alone.

## This kit's own gates

```text
python -B scripts/sync_skill_resources.py . --check
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/validate.py .
python -B scripts/route_eval.py .
python -B scripts/secret_scan.py .
python -B scripts/policy_check.py .
python -B scripts/external_collision_eval.py .
python -B scripts/doctor.py --check --root .
```

## Verdict mapping

| Observation | Verdict |
|---|---|
| Command ran, exit 0, expected fresh artifact inspected | `PASS` |
| Command ran, non-zero exit, or artifact missing/stale/error-laden | `FAIL` |
| Tool, runner, credential, device, editor, or service unavailable | `BLOCKED` |
| Result from an earlier session that cannot be re-run now | `Snapshot`, not `PASS` |

## Evidence

Record the claim, the exact command, the working directory, the environment and version snapshot, the commit plus dirty-file count, the exit code, the artifact path with size, hash, and timestamp, the freshness check, and an explicit statement of what the check does not prove.
