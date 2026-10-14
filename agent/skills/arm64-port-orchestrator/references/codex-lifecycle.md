# Codex Lifecycle Adapter

Use this reference on Codex, where the Claude Workflow scriptlets cannot run.
The adapter externalizes state and evidence; it does not replace the semantic
work performed by EasyWoS leaf skills.

## Initialize and resume

```powershell
node scripts/codex/lifecycle-driver.js init `
  --change openspec/changes/<change> `
  --project <project-root> `
  --target arm64-windows

node scripts/codex/lifecycle-driver.js next `
  --change openspec/changes/<change>
```

`next` returns the current phase and required evidence. Perform that bounded
action, write its structured evidence, and submit it with the matching key.
The driver refuses cross-phase jumps and hashes every accepted artifact.

```powershell
node scripts/codex/lifecycle-driver.js submit `
  --change openspec/changes/<change> `
  --phase MATCH --key matcher --evidence evidence/matcher.json
```

If source, matcher rules, combined specs, or an accepted upstream artifact
changes, invalidate the affected phase and every downstream phase:

```powershell
node scripts/codex/lifecycle-driver.js invalidate-from `
  --change openspec/changes/<change> `
  --phase MATCH --reason "matcher/spec updated"
```

## Dispatch

Prepare one immutable request per porting item:

```powershell
node scripts/codex/dispatcher-adapter.js prepare `
  --matched <matched.yaml> `
  --matcher evidence/matcher.json `
  --specs skills/combined-spec-summary.yaml `
  --item <porting-item-id> `
  --out dispatch/<id>-attempt-1.request.yaml
```

Load and follow the request's leaf skills in Codex. After applying the result,
record the producer session and patch or changed-file hashes:

```powershell
node scripts/codex/dispatcher-adapter.js record-result `
  --request dispatch/<id>-attempt-1.request.yaml `
  --producer-session <session-id> `
  --patch <patch-file> `
  --out dispatch/<id>-attempt-1.result.yaml
```

After every item has a result, generate the dispatch manifest and submit it to
the lifecycle driver:

```powershell
node scripts/codex/dispatcher-adapter.js summary `
  --dir dispatch --matcher evidence/matcher.json `
  --out evidence/dispatch-manifest.yaml
```

## Performance evidence

The only archivable statuses are:

- `CONVERGED`: profiler ran and the stop condition was met.
- `STALLED`: profiler ran, but an explicit blocker remains.
- `SKIPPED_BY_USER`: the user explicitly selected `--no-profile`.

`PAUSED_NEEDS_ADMIN`, `NO_WORKLOAD`, `PROFILE_FAILED`, and `NOT_STARTED` block
archive. A profiler-backed result references `baseline.etl`,
`baseline.speedscope.json`, and `PERF-PROGRESS.md` with optional hashes.

## Archive

```powershell
node scripts/codex/archive-gate.js `
  --change openspec/changes/<change> --strict
```

The gate checks matcher provenance, dispatch chains, x64 and ARM64 complete
build/test evidence, non-zero test discovery, source fingerprints, red→green
negative control, independent producer/verifier sessions, performance terminal
state, artifact hashes, and `openspec validate --strict`. Failure writes
`ARCHIVE-GATE-REPORT.md` and returns non-zero. Only `ARCHIVE_READY` may proceed
to OpenSpec archive; record its result with `lifecycle-driver.js
archive-complete`.
