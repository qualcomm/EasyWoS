# Outer Loop — Whole-Project Build → Project-Test → Auto-Fix

This is the algorithm the orchestrator owns (SKILL.md §7–§8). It is **implemented
as deterministic code** in [../assets/outer-loop-driver.js](../assets/outer-loop-driver.js)
and run via the Workflow tool — this document is the spec/rationale for that
script, not a set of steps for an LLM to execute by hand. The loop control,
fan-out, retry counters, and exit criteria are the orchestration-layer (①)
decision and therefore live in code; agents only fill in the ② fix and ③ verify
decisions. It is deliberately generic: the script names no project, kernel, or
build file — every project fact arrives through `args`.

## Terminology

- **Outer iteration**: one full `configure → compile → link → project-test`
  pass plus the fixes applied in response to its failures.
- **Owning file**: the single file whose change most directly fixes a failure
  (the kernel that miscompiles, the dispatch TU with the bad prototype, the
  CMakeLists that omits a source). The routing key.
- **Oracle**: the check that decides correctness. In the inner loop it is the
  isolated gtest fixture; in the outer loop it is the **project's own
  test/bench suite**.

## Failure classification schema

Each distinct root failure (dedupe cascade lines) is one record:

```yaml
category:  build-system | compile-asm | compile-cpp | link-abi | test-failure | other
stage:     configure | compile | link | test
targetFile: <absolute path of the owning file>     # routing key
symbol:    <function/symbol name if relevant, else empty>
message:   <exact compiler/linker/test error line(s)>
excerpt:   <a few lines of surrounding build-log context>
kernelId:  <porting_item id, when the failure traces to a ported kernel>
```

`kernelId` is what lets a `test-failure` re-enter the inner loop: it maps the
project-test regression back to the porting_item so it can be re-dispatched.

## Routing table (which fixer owns which category)

| category | owning fixer | action |
|---|---|---|
| `build-system` | `enable-windows-arm64` + orchestrator §6 | fix build files / ARM64 flag / source registration; re-detect |
| `compile-asm` | leaf skill (asm-x64-to-arm64 / x64-to-arm64-asm-porting) via targeted edit | fix the `.S`/`.asm` owning file, apply asm discipline |
| `compile-cpp` | targeted C++ edit mirroring the project's arch path | fix the dispatch TU / header |
| `link-abi` | orchestrator §6 + leaf skill | fix the symbol's owner: export name, prototype, or registration |
| `test-failure` | **inner loop re-entry** via dispatcher `--feedback` | write feedback file, re-dispatch the `kernelId` item (project test = oracle) |
| `other` | escalate | if not confidently classifiable, do not guess-fix; report |

## The `test-failure` bridge to the inner loop

A project-test regression is NOT fixed by hand-editing the kernel blindly. It is
fed back through the SAME mechanism the inner loop uses (easywos-spec §8 +
dispatcher §2.7), so the leaf skill re-ports the kernel knowing exactly what the
project's test observed:

1. Write `feedback/<kernelId>.attemptN.yaml` in the dispatcher §2.7.1 schema:
   `stage: test`, `failure_kind: assertion|crash|...`, verbatim truncated
   `detail` (the project test's failure output), `failing_fixtures` (the project
   test names), and a `hypothesis` if diagnosable.
2. Re-dispatch: `/dispatcher-skill <kernelId> --specs … --source <matched-yaml> --feedback feedback/<kernelId>.attemptN.yaml`.
3. Respect the per-kernel retry budget K (`--inner-retry-K`). On exhaustion mark
   the kernel `[NEEDS REVIEW]` and stop retrying it — never let one kernel stall
   the outer loop.

The only difference from §5's inner loop: the oracle is the project's real suite,
not the isolated gtest. Everything else (feedback schema, retry budget, terminal
exit) is reused.

## One-iteration pseudocode (as implemented in the driver)

Note the ②/③ split: a fixer agent applies a change, then a **separate**
verifier agent must independently confirm it before the loop trusts it and
rebuilds. The maker never grades its own work.

```
for iter in 1..MAX_OUTER_ITERS:
    # --- objective gate: red/green decided by tools, not by an agent ---
    result = run(build_cmd) ; if ok: result += run(test_cmd)
    if result.allClean and result.tests.failed == 0:
        return CONVERGED
    failures = classify(result)              # structured records (schema above)
    if failures.empty: return STALL("no actionable errors")   # never loop blind

    if sameSignatureAsLastIter(failures): staleCount++ else staleCount = 0
    if staleCount >= STALE_STOP: return STALL("failure signature unchanged")

    groups = groupBy(failures, f => f.targetFile)   # one fixer per owning file
    groups = dropRetryExhausted(groups)             # kernels past budget K -> NEEDS REVIEW
    if groups.empty: return STALL("only retry-exhausted kernels remain")

    # --- ② task layer: bounded fixer per file, in parallel ---
    fixes = parallel(groups, (file, fs) =>
        any(fs is test-failure) ? innerLoopReentry(kernelId, fs)   # dispatcher --feedback, budget K
                                : routedFixer(fs).fix(file, fs))    # build-system / leaf-skill edit
    applied = fixes.filter(f => f.applied)
    if applied.empty: return STALL("no fixer could apply a change")

    # --- ③ judgement layer: INDEPENDENT adversarial verifier per fix ---
    verdicts = parallel(applied, fix =>
        independentVerifier(fix))            # different agent; refute or watch-test-go-red
    confirmed = verdicts.filter(v => v.verified)
    appendProgress(OUTER_PROGRESS_md, failures, applied, confirmed, refuted=verdicts\confirmed)
    if confirmed.empty: return STALL("all fixes refuted by verification — approach exhausted")
    # only verified fixes survive -> next iteration's objective gate re-checks
return STALL("outer iteration cap reached")
```

## Negative-control gate (mandatory before trusting any test fix)

Inherited from the global working principle and easywos-spec §7.6. A green
project-test after a `test-failure` fix is not trusted until the same test has
been observed **red**:

1. Perturb the reference/expected side (not the kernel) so the fixed test must
   disagree — or, for a suite, perturb all references by `+1` and confirm the
   whole suite goes red.
2. Run; confirm `[FAILED]` / non-zero exit. If it stays green, the test is not
   wired to the kernel (dead fixture, self-compare, kernel not linked) — that is
   the real bug; fix the wiring before trusting anything.
3. Revert, rebuild clean; only now does green count.

Record which tests were shown red. A test that passed but was never shown red is
reported as **unverified**, not passing.

**Who runs the negative control matters.** It is performed by the *independent
verifier* agent (③), not by the fixer that wrote the change. Decision ≠
verification: the agent that made a fix has a motive to declare success, so it
does not get to grade itself. The verifier defaults to `verified=false` and must
produce a counterexample (non-test fixes) or personally observe the red
(test-failures) to flip to true.

## Cross-round state: OUTER-PROGRESS.md

Because each build/fix/verify agent turn is a fresh context, cross-round
decisions MUST be externalized or they are lost. The driver appends one record
per iteration to `openspec/changes/<change>/OUTER-PROGRESS.md`:

- failures seen this round (signatures),
- fixes applied, and which were **verified** vs. **refuted (with the
  counterexample)**.

The refuted list is the "dead ends" ledger: a later iteration reads it so it does
not re-attempt an approach an independent verifier already disproved. This is
what makes the no-progress guard meaningful (it explains *why* a signature
persists) and the run resumable/debuggable. Per-kernel `feedback/*.yaml` carries
the same signal down into the inner loop.

## Terminal states (the loop ALWAYS ends in one)

- `CONVERGED` — whole project builds + project suite green + fixed tests shown
  red by the independent verifier → orchestrator §9 (archive).
- `STALL(reason)` — one of: iteration cap hit; no actionable failures; zero fixes
  applied; failure signature unchanged across `staleStop` rounds; **all fixes
  refuted by independent verification**; only retry-exhausted (`[NEEDS REVIEW]`)
  kernels remain. Do NOT archive. Report: reason, the surviving failure records
  (category + owning file + message), and the single most likely next action.

A loop that neither converges nor stalls is a bug in the driver, not a valid
state — every path in `outer-loop-driver.js` returns one of the two.
