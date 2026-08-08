# Intake → Debug → Verify

1. Route through `studio-project-intake`; emit task packet and risk tier.
2. Use `evidence-first-debugging`; reproduce and rank falsifiable hypotheses before mutation.
3. For changes, route through `safe-project-mutation` and obey risk approval.
4. Use `build-and-runtime-verification`; capture command, exit code, artifact and limitations.
5. Finish with `studio-handoff` using Verified/Snapshot/Unverified/BLOCKED labels.

This is an entry point only; canonical workflow details remain in the named skills.
