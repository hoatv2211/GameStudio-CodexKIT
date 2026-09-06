# Graphify Code Intelligence Dogfood

## Scope and safety

Snapshot date: 2026-08-26. Graphify 0.9.50 was evaluated against an authorized private Unity project as a read-only, AST-only code-intelligence dogfood snapshot. This case study promotes only the sanitized evidence already observed; no current rerun, provider operation, or project mutation was performed.

Current dogfood scope is one authorized private Unity project only.

The owner-constrained second private project is excluded; no data was accessed or reported.

## Authorized private Unity project evidence

- Snapshot: observed snapshot size was 88,955 nodes and 244,284 edges.
- Snapshot of a locally Verified comparison: source truth contained 33 known C# TaskChangeNotify constructor sites. The graph comparison found 28 matched and 0 extras, yielding sample precision 100% (28/28=100%) and recall 28/33=84.85%.
- Snapshot: sampled misses included generated wrappers and a C# to generated-Lua to Lua-handler path. Parser coverage and generated-authority discovery were incomplete.
- Snapshot: raw `_origin=ast` results included both `EXTRACTED` and `confidence=INFERRED` records. Inferred edges are never Verified merely because the provider emitted them.
- BLOCKED: project-wide accuracy cannot be inferred from the bounded C# samples. Generated, Lua, and cross-language coverage remains incomplete.
- BLOCKED: C++ coverage was not demonstrated by the current project snapshot.

The C# result is a bounded signal only. Generalizing the observed sample to all Unity/C# code, generated code, Lua, C++, or other languages is Unverified.

## Cross-repository and rollout verdict

Cross-repository accuracy is BLOCKED because no separately bound repositories with named source-truth cases were demonstrated.

Graphify remains experimental and opt-in. Deep integration is BLOCKED. Do not rerun until cache and isolation governance permits a new governed dogfood session; any new dogfood under this constraint uses only an authorized private Unity project.

## Evidence handling

The counts, metrics, and sampled misses above are durable Snapshot facts that originated from a locally Verified comparison. Private repository binding and artifact hash are omitted, so this document does not independently prove current freshness. Broader accuracy claims are Unverified. Missing generated, Lua, C++, cross-language, cross-repository, and project-wide proof stays BLOCKED. Current use and deep integration remain BLOCKED.

This durable record contains no raw provider output, copyrighted upstream documentation, private absolute paths, secrets, mutation commands, or project-local file inventory. Raw local evidence remains ignored and is not distributed.
