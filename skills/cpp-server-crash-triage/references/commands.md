# C++ Crash Triage Command Reference

Work on authorized local copies of the dump, executable, and symbols. Dumps may contain credentials or player data.

## Snapshot identity

```powershell
Get-FileHash -LiteralPath '.\GameServer.exe' -Algorithm SHA256
Get-FileHash -LiteralPath '.\server.dmp' -Algorithm SHA256
git rev-parse HEAD
```

```bash
sha256sum ./game-server ./core
git rev-parse HEAD
```

## Windows dump inspection

```powershell
dumpchk.exe .\server.dmp
cdb.exe -z .\server.dmp -y 'srv*C:\Symbols*https://msdl.microsoft.com/download/symbols;D:\BuildSymbols' -c '!analyze -v; .ecxr; kb; lm; q'
```

Confirm that module timestamps, image hashes, and PDB identity match the crashing build before trusting the stack.

## Linux core inspection

```bash
gdb -batch ./game-server ./core \
  -ex "set pagination off" \
  -ex "info files" \
  -ex "thread apply all bt full"
```

```bash
addr2line -e ./game-server -f -C 0xADDRESS
llvm-symbolizer --obj=./game-server 0xADDRESS
```

## Normalized signature

Feed ordered module/function/source frames to the bundled `scripts/crash_triage.py`. Preserve raw debugger output separately; normalization must not discard frame order or symbol limitations.

## Evidence

Record dump hash, executable hash, build identity, debugger version, symbol source, normalized stack signature, first actionable frame, ranked hypotheses, and next bounded reproduction step.

Do not call a raw address a stable signature. Do not claim root cause from mismatched or missing symbols. Do not upload dumps to external services without authorization.
