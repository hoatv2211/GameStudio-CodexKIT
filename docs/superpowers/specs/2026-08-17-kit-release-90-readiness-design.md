# KIT Release 90+ Readiness Design

**Status:** Approved for implementation on 2026-08-17.

## Goal

Raise GameStudio-CodexKIT to a defensible 90+ production-readiness score by removing unsupported PASS paths, making mutation and generation transactional, producing strict evidence from the reference FPC project, and turning lifecycle readiness into an explicit release gate.

## Operating Constraints

- Work directly in the existing dirty KIT and FPC worktrees.
- Preserve all unrelated tracked and untracked changes.
- Do not branch, commit, push, publish, deploy, sign, or start destructive database/service operations.
- Treat FCR in the request as the reference FPC project.
- Use the configured Unity relay with `relay_win.exe --mcp`, pinned to `<FPC_ROOT>/client/LineRWebGL`.
- Keep missing external evidence `BLOCKED`; never lower a gate to manufacture a score.

## Release 90+ Acceptance Contract

The release-readiness score may be reported as 90+ only when all of the following are true:

1. No open P1 or P2 finding remains in mutation, restore, adapter generation, pack generation, promotion validation, or release preflight.
2. The complete KIT deterministic gate set exits zero.
3. Promotion evidence is self-contained, strict-schema-valid, artifact-bound, hash-valid, and accepted by both `validate.py` and `catalog_audit.py`.
4. Release preflight binds every PASS check to one candidate identity, source snapshot, build identity, artifact hash, owner, command, timestamp, and evidence bundle.
5. FPC static localization dogfood passes and Unity runtime dogfood contains real Editor/Test Framework/PlayMode evidence rather than an availability flag.
6. FPC has executable validation commands for its active specialist lanes.
7. Tier-B, behavior, pressure, sanitized session-history, originality, and catalog lifecycle gates either pass for the release scope or remain explicit blockers that prevent a 90+ release claim.

## Architecture

### 1. Transactional Mutation Restore

`scripts/safe_mutation.py` remains canonical. Restore uses a durable progress journal and a per-operation quarantine under the owned backup directory. Each target is moved atomically into quarantine, verified against the applied hash, and then replaced by its verified backup or left absent for a create operation. A failure rolls completed operations back from quarantine. A process interruption leaves a resumable or explicit manual-recovery state; it never leaves a mixed workspace with an `applied` manifest and no progress record.

Generated copies are updated only through `scripts/sync_skill_resources.py`.

### 2. Transactional Adapter And Pack Generation

Registry IDs, pack IDs, capability paths, source roots, and destinations are validated as safe contained paths before any output mutation. Generators render the complete replacement tree in a sibling staging directory, validate generated ownership and manifest contents, and then swap it into place. The previous managed output is retained until the new tree is complete. Failed rendering or swapping restores the previous output and removes only owned staging artifacts.

### 3. Candidate-Bound Release Evidence

Release preflight accepts a structured payload containing one candidate identity and the mandatory gate set. Evidence entries contain relative path and SHA-256. Every PASS gate names the same candidate ID, command, exit code, timestamp, owner, and artifacts. Candidate identity includes version, source snapshot, build ID, and primary artifact digest. Empty JSON, placeholder text, stale evidence, mismatched candidates, missing hashes, missing rollback/monitoring details, or duplicate gates cannot PASS.

### 4. Strict Promotion Evidence

Promotion validation reuses the governed dogfood schema and evaluator rather than a weaker metadata-only check. A dogfood result artifact is accepted only when selected cases pass strict evaluation against a self-contained artifact root. The FPC beta evidence bundle includes the referenced snapshot, command logs, reports, verdicts, and matching hashes. If a bundle cannot be made distributable without leaking private paths, the capability returns to `experimental` until valid evidence exists.

### 5. Unity MCP FPC Certification

The certification runner does not accept `--mcp-available` as evidence. A Unity runtime result is produced from an actual MCP transcript containing:

- active Unity instance and project identity;
- editor readiness and compilation state;
- project information and selected custom tools;
- Unity Test Framework EditMode result;
- controlled PlayMode entry and exit;
- localization runtime assertion for the target prefab/text path;
- console error/warning capture;
- screenshot or equivalent visual artifact when the running scene is renderable;
- exact commands/tool calls, timestamps, verdict, restore statement, and hashes.

The relay is pinned with `--project-path` so concurrent Unity projects cannot receive commands.

### 6. Lifecycle And Maturity

CI keeps deterministic gates separate from lifecycle readiness, but adds a required release-readiness job for release tags or explicit dispatch. Nightly output includes catalog and originality reports rather than only pre-run BLOCKED files. Core skills advance one adjacent maturity level at a time and only when promotion evidence covers their actual runtime targets. Broad specialist coverage alone does not justify maturity promotion.

## Error Handling

- Concurrent restore drift: preserve the concurrent target and abort without claiming restored.
- Restore interruption: retain quarantine/progress evidence and resume or report manual recovery.
- Invalid generator ID/path: fail before creating, deleting, or replacing output.
- Generator rendering/swap failure: restore the previous managed output.
- Invalid release or promotion evidence: deterministic FAIL with field/path/hash reason.
- Unity unavailable or disconnected: runtime case remains BLOCKED with connection evidence.
- Unity compilation/test/PlayMode error: runtime case FAILS with console and test artifacts.

## Test Strategy

- Red-green regression tests reproduce every current P1/P2 finding.
- Safe-mutation tests cover concurrent restore drift, failures at each operation boundary, rollback, resume, and manifest/progress integrity.
- Packaging tests cover traversal through pack ID, skill ID, capability ID/path, failed rendering, failed swap, and unmanaged directory preservation.
- Release tests reject semantically empty evidence, cross-candidate mixing, hash drift, stale timestamps, incomplete monitoring/rollback, defects, and waivers.
- Promotion tests run the strict dogfood evaluator against the frozen artifact bundle and fail if any referenced artifact is absent or modified.
- Unity runtime evidence is validated offline after collection so a copied or incomplete transcript cannot PASS.
- Full KIT and FPC gates run after focused suites.

## Score Model

The final report keeps capability completeness and production readiness separate. Production readiness is weighted toward mutation/generator safety, evidence integrity, real runtime dogfood, and lifecycle gates. Passing unit tests alone cannot compensate for an open P1 or a fabricated/unsupported PASS path.

## Delivery

The implementation ends with fresh commands, exit codes, artifact paths, a list of remaining BLOCKED items, a new production-readiness score, and no commit or push.
