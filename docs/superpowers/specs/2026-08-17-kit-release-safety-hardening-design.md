# Kit Release Safety Hardening Design

**Status:** Approved for implementation on 2026-08-17.

## Goal

Prevent unsupported PASS verdicts and unsafe generator or mutation behavior before the next distributed plugin release.

## Scope

- Revalidate target state during Windows atomic-replace retries and retry manifest state writes safely.
- Make release preflight require a complete, evidence-backed mandatory gate set.
- Make governed dogfood results compatible with Codex strict Structured Outputs and bind PASS artifacts to existing files and hashes.
- Prevent adapter and pack outputs from overlapping canonical skill sources.
- Preserve unmanaged pack files even when their body mentions a generated marker.
- Keep adapter and pack frontmatter handling consistent with the repository parser.
- Regenerate bundled helpers, update dogfood documentation, and bump the plugin version to `1.3.3`.

## Non-Goals

- Fabricating Tier-B, behavior, pressure, session-history, or dogfood PASS evidence.
- Running live Unity builds, services, databases, deployments, or publication actions.
- Making lifecycle audits green without their required external evidence.
- Refactoring unrelated skills, registries, adapters, or project-local FPC files.

## Design

### Safe Mutation

`scripts/safe_mutation.py` remains the canonical implementation. Target replacement retries will invoke exact target safety and pre-state validation before every attempt. If another process changes or creates the target during a retry window, apply aborts and preserves the concurrent content rather than replacing it.

Manifest writes will use a separate bounded retry helper around the captured atomic replace callable. This keeps manifest failure injection independent from target replacement tests and covers prepared, applied, rolled-back, and restored state transitions. Persistent contention retains the existing rollback and manual-recovery behavior.

The canonical helper will be propagated only through `scripts/sync_skill_resources.py` into:

- `skills/safe-project-mutation/scripts/safe_mutation.py`
- `skills/studio-project-scaffold/scripts/safe_mutation.py`

### Release Preflight

`evaluate_release_preflight` keeps a list-based check interface but gains an explicit evidence root and a mandatory default gate set:

- `candidate`
- `build`
- `tests`
- `security`
- `performance`
- `compatibility`
- `monitoring`
- `rollback`
- `approvals`

Check IDs must be unique and non-empty. A PASS check requires a non-empty command, exit code zero, an ISO-8601 timestamp, a named owner, and one or more artifact paths. Artifact paths must be relative to the approved evidence root, remain inside it after resolution, and identify existing files. FAIL or BLOCKED checks require a reason. Empty input, missing mandatory checks, malformed evidence, or an unavailable evidence root cannot produce PASS.

### Governed Dogfood

`evals/schema/dogfood-result.schema.json` will use a strict-compatible object root with one required `results` property. Every declared result property will be required; fields unavailable for BLOCKED or FAIL results will use nullable unions. Artifact objects will require `kind`, relative `path`, and a SHA-256 digest.

`scripts/dogfood_eval.py` will:

1. Validate the strict wrapper against the result schema.
2. Continue reading legacy array files only for local diagnostic compatibility; legacy input cannot generate promotion summaries.
3. Resolve every PASS artifact under an explicit or default evidence root.
4. Reject absolute paths, traversal, missing files, non-files, and digest mismatches.
5. Normalize summary artifacts with their approved root and digest.

`scripts/catalog_audit.py` will re-resolve and hash every dogfood summary artifact before accepting it as `Verified`. A stale, moved, missing, or modified artifact makes the summary invalid.

### Generator Safety

Standard adapters and pack builders will preflight output paths before clearing or writing anything. Output is rejected when it equals, contains, or is contained by any canonical skill source being walked.

Pack cleanup will use format-aware ownership checks:

- `manifest.json`: parsed `_generated` value must match exactly.
- `SKILL.md`: marker must occupy the generated frontmatter header position.
- Script/YAML/TOML resources: hash-comment marker must be the first line.
- Markdown/text resources: HTML-comment marker must be the first line.

A marker appearing later in unmanaged content never grants deletion ownership.

Adapter and pack skill generation will accept the same opening frontmatter delimiter syntax as `scripts/common.py`, while always emitting a normalized `---` first line followed by the generated marker.

## Compatibility

- Existing canonical skills remain valid and generate the same parsed frontmatter and body.
- Existing BLOCKED legacy dogfood arrays remain readable for diagnosis but cannot create promotion evidence.
- New PASS dogfood runs must use the strict wrapper and hashed artifacts.
- Release-preflight callers must provide the mandatory gate set and an evidence root; permissive legacy PASS behavior is intentionally removed.
- Distributed helper changes require plugin version `1.3.3` to invalidate installed caches.

## Error Handling

- Concurrent target drift: abort mutation and preserve the concurrent target.
- Persistent Windows replace contention: retain bounded failure, rollback, and manual-recovery evidence.
- Missing release or dogfood evidence: return FAIL or BLOCKED, never PASS.
- Invalid schema, path traversal, missing file, or digest mismatch: deterministic FAIL with an actionable reason.
- Generator output overlap or unmanaged output content: refuse before deletion or source-tree mutation.

## Test Strategy

Use red-green TDD for every behavior:

- Update and create races during target retry preserve concurrent data.
- Transient manifest contention succeeds; persistent contention follows existing recovery semantics.
- Empty, partial, duplicate, malformed, or pathless release checks cannot PASS.
- Strict dogfood schema passes the Structured Outputs subset checks.
- Unknown fields, invalid types, missing artifacts, traversal, and hash drift fail dogfood evaluation.
- Legacy BLOCKED arrays remain diagnostic-only.
- Catalog audit rejects missing or modified dogfood artifacts.
- Adapter and pack outputs nested in source are refused without changing the source tree.
- Marker text in an unmanaged pack file does not authorize deletion.
- Parser-valid frontmatter variants generate normalized valid frontmatter.

Focused suites run after each component, followed by the complete repository gates from `AGENTS.md`, lifecycle audits, `git diff --check`, and a final resource synchronization check.

## Delivery

No commit or publish action is included. The final handoff will list changed canonical and generated paths, tests and exit codes, remaining BLOCKED lifecycle evidence, and the exact next release action requiring user approval.
