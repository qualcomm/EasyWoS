export const meta = {
  name: 'arm64-outer-loop-driver',
  description: 'Deterministic skeleton for the ARM64 port OUTER loop: build the whole project, run its own test suite, classify failures, route each to a fixer agent, then adversarially VERIFY every fix with an independent agent, rebuild — until green or cap. Generic: all project facts come from args, nothing is hardcoded.',
  phases: [
    { title: 'Build', detail: 'configure -> compile -> link -> run the project OWN test/bench suite' },
    { title: 'Fix', detail: 'one fixer agent per owning-file (task-layer decision, inside a bounded box)' },
    { title: 'Verify', detail: 'independent adversarial verifier per fix (decision != verification)' },
  ],
}

// ============================================================
// DETERMINISTIC ORCHESTRATION LAYER (this is CODE, not an LLM decision).
// The loop, the fan-out, the retry counters, the convergence/stall criteria,
// and the exit condition are all hardcoded here. Agents only FILL IN the two
// delegated decisions: "how do I fix this one file" (§Fix) and "is this fix
// actually correct" (§Verify). "Should we loop again?" is decided by this code.
// ============================================================

// ---- args contract (passed verbatim by the orchestrator skill) -------------
// {
//   projectPath:   string   // absolute root of the project being ported
//   buildCmd:      string   // command that builds the WHOLE project for ARM64
//   testCmd:       string   // command that runs the project's OWN test/bench suite
//   matchedYaml:   string   // path to <report>-matched.yaml (for --feedback re-dispatch)
//   stateDir:      string   // openspec/changes/<change>/ — where state + progress + feedback live
//   maxOuterIters?: number  // default 12
//   innerRetryK?:  number   // default 3  (per-kernel budget, shared with easywos-spec §8)
//   staleStop?:    number   // default 2  (consecutive identical-signature rounds -> STALL)
// }
const A = args || {}
const PROJECT = A.projectPath
const BUILD_CMD = A.buildCmd
const TEST_CMD = A.testCmd
const MATCHED = A.matchedYaml
const STATE_DIR = A.stateDir
const MAX_ITERS = A.maxOuterIters || 12
const K = A.innerRetryK || 3
const STALE_STOP = A.staleStop || 2

if (!PROJECT || !BUILD_CMD || !TEST_CMD || !STATE_DIR) {
  throw new Error('outer-loop-driver: missing required args (projectPath, buildCmd, testCmd, stateDir). The orchestrator resolves these in SKILL.md §7.1 before invoking.')
}

const PROGRESS = `${STATE_DIR}/OUTER-PROGRESS.md`
const FEEDBACK_DIR = `${STATE_DIR}/feedback`

// ---- schemas: force structured returns, validated at the tool layer --------
const BUILD_SCHEMA = {
  type: 'object',
  required: ['success', 'stage', 'summary', 'failures'],
  properties: {
    success: { type: 'boolean', description: 'true ONLY if configure+build+link clean AND the project test suite ran with zero failures.' },
    stage: { type: 'string', enum: ['configure', 'compile', 'link', 'test', 'done'] },
    summary: { type: 'string' },
    testResults: {
      type: 'object',
      properties: { ran: { type: 'boolean' }, passed: { type: 'integer' }, failed: { type: 'integer' }, total: { type: 'integer' } },
    },
    failures: {
      type: 'array',
      description: 'One entry per DISTINCT root failure (dedupe cascade lines). Empty iff success=true.',
      items: {
        type: 'object',
        required: ['category', 'targetFile', 'message'],
        properties: {
          category: { type: 'string', enum: ['build-system', 'compile-asm', 'compile-cpp', 'link-abi', 'test-failure', 'other'] },
          targetFile: { type: 'string', description: 'Absolute path of the file that OWNS the bug — the routing key.' },
          symbol: { type: 'string' },
          kernelId: { type: 'string', description: 'porting_item id when the failure traces to a ported kernel (required for test-failure so it can re-enter the inner loop).' },
          message: { type: 'string', description: 'Exact compiler/linker/test error line(s).' },
          excerpt: { type: 'string' },
        },
      },
    },
  },
}

const FIX_SCHEMA = {
  type: 'object',
  required: ['applied', 'description', 'filesChanged'],
  properties: {
    applied: { type: 'boolean', description: 'true if you applied a concrete change addressing the ROOT cause.' },
    description: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    signature: { type: 'string', description: 'Short stable signature of the failure you addressed (category+file+symbol) — used to detect no-progress loops.' },
    note: { type: 'string' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['verified', 'reason'],
  properties: {
    verified: { type: 'boolean', description: 'true ONLY if you independently confirmed the fix is correct AND (for test-failures) watched the test go RED under a deliberate perturbation then GREEN after revert.' },
    negativeControlObserved: { type: 'boolean', description: 'true if you actually saw the relevant test/check fail on a wrong input. Required true to trust a test-failure fix.' },
    reason: { type: 'string', description: 'What you checked and why the fix does or does not hold. Default to verified=false when uncertain.' },
    counterexample: { type: 'string', description: 'If verified=false, the concrete case that refutes the fix (or why the negative control could not be shown).' },
  },
}

// ---- helpers ---------------------------------------------------------------
function sig(f) { return `${f.category}|${(f.targetFile || '').split(/[\\/]/).pop()}|${f.symbol || ''}` }

// ============================================================
// OUTER LOOP — deterministic. Every path ends in CONVERGED or STALL(reason).
// ============================================================
const kernelAttempts = {}          // kernelId -> attempts spent (shared budget K)
const history = []
let lastSignatureSet = ''
let staleRounds = 0
let outcome = null

log(`[driver] project=${PROJECT}`)
log(`[driver] build=${BUILD_CMD}`)
log(`[driver] test =${TEST_CMD}`)
log(`[driver] append cross-round progress to ${PROGRESS}`)

for (let iter = 1; iter <= MAX_ITERS; iter++) {
  // ---------- Build stage (objective gate — NOT an agent opinion) ----------
  phase('Build')
  const build = await agent(
    `Run the ARM64 build + the project's OWN test suite and report results. Bash shell available.

Working dir: ${PROJECT}
1. Build (whole project, ARM64):  ${BUILD_CMD}
2. Test  (project's own suite):   ${TEST_CMD}

Capture ALL output. Then:
- If configure+build+link are clean AND the test suite ran with ZERO failures: success=true, stage="done", failures=[].
- Otherwise success=false, stage = furthest stage reached, and one failures[] entry per DISTINCT root cause. Set targetFile to the file that OWNS the bug (the routing key). For a test-failure, set kernelId to the porting_item whose kernel the failing test exercises (trace it from the test/symbol name). Put the exact error in message.

Do NOT fix anything — you only build, run, and report.`,
    { label: `build#${iter}`, phase: 'Build', schema: BUILD_SCHEMA }
  )

  if (!build) {
    history.push({ iter, event: 'build-agent-null' })
    outcome = { status: 'STALL', reason: 'build agent returned nothing (skipped/died)' }
    break
  }

  const tr = build.testResults
  log(`[iter ${iter}] stage=${build.stage} success=${build.success}` +
      (tr && tr.ran ? ` tests=${tr.passed}/${tr.total} (${tr.failed} failed)` : '') +
      ` failures=${(build.failures || []).length}`)

  if (build.success) {
    history.push({ iter, stage: 'done', tests: tr })
    outcome = { status: 'CONVERGED', iter, tests: tr }
    break
  }

  const failures = build.failures || []
  if (failures.length === 0) {
    outcome = { status: 'STALL', reason: 'success=false but no actionable failures reported' }
    history.push({ iter, event: 'no-actionable-failures', summary: build.summary })
    break
  }

  // ---------- No-progress guard (deterministic convergence criterion) ------
  const sigSet = failures.map(sig).sort().join(' ;; ')
  if (sigSet === lastSignatureSet) {
    staleRounds++
    if (staleRounds >= STALE_STOP) {
      outcome = { status: 'STALL', reason: `failure signature unchanged across ${STALE_STOP + 1} iterations: ${sigSet}` }
      history.push({ iter, event: 'stale', sigSet })
      break
    }
  } else {
    staleRounds = 0
    lastSignatureSet = sigSet
  }

  // ---------- Group by owning file: one fixer per file, no write races -----
  const byFile = new Map()
  for (const f of failures) {
    const key = f.targetFile || `unknown:${f.category}`
    if (!byFile.has(key)) byFile.set(key, [])
    byFile.get(key).push(f)
  }
  log(`[iter ${iter}] routing ${failures.length} failure(s) -> ${byFile.size} fixer agent(s)`)

  // Budget check for test-failures BEFORE dispatching (owned by this code).
  const groups = []
  for (const [file, fs] of byFile) {
    const tfKernel = fs.find(x => x.category === 'test-failure' && x.kernelId)?.kernelId
    if (tfKernel) {
      kernelAttempts[tfKernel] = (kernelAttempts[tfKernel] || 0) + 1
      if (kernelAttempts[tfKernel] > K) {
        log(`[iter ${iter}] kernel ${tfKernel} exhausted retry budget K=${K} -> [NEEDS REVIEW], skipping`)
        history.push({ iter, kernelId: tfKernel, event: 'retry-exhausted' })
        continue // do not fix again; let it surface as NEEDS REVIEW at exit
      }
    }
    groups.push([file, fs, tfKernel])
  }

  if (groups.length === 0) {
    outcome = { status: 'STALL', reason: 'all remaining failures are retry-exhausted kernels ([NEEDS REVIEW])' }
    break
  }

  // ---------- ② TASK-LAYER: fixer agents (bounded box) ---------------------
  phase('Fix')
  const fixes = await parallel(groups.map(([file, fs, tfKernel]) => () => {
    const isAsm = fs.some(x => ['compile-asm', 'link-abi', 'test-failure'].includes(x.category))
    const box = tfKernel
      ? `This is a TEST-FAILURE traced to ported kernel "${tfKernel}". Re-enter the inner porting loop: write ${FEEDBACK_DIR}/${tfKernel}.attempt${kernelAttempts[tfKernel]}.yaml in the dispatcher §2.7.1 schema (stage: test, failure_kind, verbatim truncated detail, failing_fixtures, hypothesis), then re-dispatch:\n  /dispatcher-skill ${tfKernel} --specs <its specs> --source ${MATCHED} --feedback ${FEEDBACK_DIR}/${tfKernel}.attempt${kernelAttempts[tfKernel]}.yaml\nThe project's own test is now the oracle. Fix the ROOT cause in the kernel; do NOT weaken the test.`
      : isAsm
        ? `ARM64 assembly / ABI fix. Apply asm-x64-to-arm64 / intrinsics discipline: AArch64 GAS syntax, Windows ARM64 C-ABI, NEON 128-bit width, by-element smull/smlal operands from v0-v15, widen (saddl/ssubl/smull) before accumulating to avoid intermediate overflow.`
        : `C++/CMake integration fix. Match the surrounding idiom and the project's ARM64 guard macros exactly; mirror the existing arch (e.g. x86) path.`
    const errList = fs.map((e, i) => `  [${i + 1}] ${e.category} sym=${e.symbol || '-'}\n      ${e.message}\n      ctx: ${e.excerpt || '-'}`).join('\n')
    return agent(
      `Fix the build/test failure(s) in ONE file. Working dir: ${PROJECT}.

TARGET FILE (the only file you may change, plus a header it owns if strictly needed): ${file}

FAILURE(S):
${errList}

BOX / METHOD:
${box}

Read the file (and its dependencies) before editing. Make the MINIMAL correct change to the ROOT cause. Do NOT touch other files — sibling failures are being fixed in parallel. Return structured output (set "signature" to ${JSON.stringify(sig(fs[0]))} or a refinement of it).`,
      { label: `fix:${file.split(/[\\/]/).pop()}#${iter}`, phase: 'Fix', schema: FIX_SCHEMA }
    ).then(fx => ({ file, fs, tfKernel, fix: fx }))
  }))

  const applied = fixes.filter(Boolean).filter(f => f.fix && f.fix.applied)
  if (applied.length === 0) {
    outcome = { status: 'STALL', reason: 'no fixer could apply a change this iteration' }
    history.push({ iter, event: 'no-fix-applied', failures: failures.map(sig) })
    break
  }

  // ---------- ③ JUDGEMENT-LAYER: independent adversarial verifier ----------
  // The agent that MADE a fix does NOT get to bless it. A separate skeptic
  // tries to REFUTE each fix and (for test-failures) must WATCH the test go red.
  phase('Verify')
  const verdicts = await parallel(applied.map(f => () => {
    const isTest = f.fs.some(x => x.category === 'test-failure')
    const adversary = isTest
      ? `Independently verify the fix to ${f.file} for failure(s): ${f.fs.map(x => x.message).join(' | ')}.
MANDATORY NEGATIVE CONTROL: in a throwaway build, perturb the test's expected/reference side (NOT the kernel) so the fixed test MUST disagree, run it, and confirm it reports [FAILED] / non-zero. Then revert and confirm GREEN. If it stays green under perturbation the test is not wired to the kernel — verified=false. Default to verified=false if you cannot personally observe the red. Do NOT trust the fixer's claim.`
      : `Independently try to REFUTE the fix to ${f.file} for: ${f.fs.map(x => x.message).join(' | ')}. Assume it is WRONG and look for a counterexample: does it actually resolve the root cause, or just mask the symptom? Re-run the relevant build/link step to confirm the specific error is gone and no new error was introduced. Default to verified=false if uncertain.`
    return agent(
      `You are an independent adversarial VERIFIER. You did NOT write this fix. Working dir: ${PROJECT}.

FIX UNDER REVIEW: ${f.fix.description}
FILES CHANGED: ${(f.fix.filesChanged || []).join(', ')}

${adversary}

Return a verdict. Being wrong here is worse than being skeptical — when in doubt, verified=false with a counterexample.`,
      { label: `verify:${f.file.split(/[\\/]/).pop()}#${iter}`, phase: 'Verify', schema: VERDICT_SCHEMA }
    ).then(v => ({ ...f, verdict: v }))
  }))

  const confirmed = verdicts.filter(Boolean).filter(v => v.verdict && v.verdict.verified)
  const rejected = verdicts.filter(Boolean).filter(v => !v.verdict || !v.verdict.verified)

  // Rejected fixes: record so next round's fixer sees the refuted approach.
  history.push({
    iter,
    stage: build.stage,
    summary: build.summary,
    applied: applied.length,
    confirmed: confirmed.length,
    rejected: rejected.map(r => ({ file: r.file, reason: r.verdict?.reason, counterexample: r.verdict?.counterexample })),
    fixes: verdicts.filter(Boolean).map(v => ({ file: v.file, kernelId: v.tfKernel, applied: v.fix?.applied, verified: v.verdict?.verified, negativeControl: v.verdict?.negativeControlObserved, description: v.fix?.description })),
  })

  // Persist cross-round progress to disk (state externalization).
  await agent(
    `Append one iteration record to the outer-loop progress log at ${PROGRESS} (create with a header if missing). Do not rewrite prior entries — append only.

## Iteration ${iter}
- Build stage reached: ${build.stage}; ${tr && tr.ran ? `tests ${tr.passed}/${tr.total}` : 'tests not run'}
- Failures this round: ${failures.map(sig).join(', ')}
- Fixes applied: ${applied.length}; independently VERIFIED: ${confirmed.length}; REFUTED: ${rejected.length}
- Refuted approaches (do NOT retry these): ${rejected.map(r => `${r.file}: ${r.verdict?.counterexample || r.verdict?.reason || 'refuted'}`).join(' | ') || 'none'}
- Verified fixes: ${confirmed.map(c => `${c.file}: ${c.fix?.description}`).join(' | ') || 'none'}

Write concisely; this file is read by future iterations to avoid repeating dead ends.`,
    { label: `progress#${iter}`, phase: 'Verify' }
  )

  if (confirmed.length === 0) {
    outcome = { status: 'STALL', reason: `all ${applied.length} fix(es) this iteration were REFUTED by independent verification — approach is exhausted` }
    break
  }

  log(`[iter ${iter}] ${confirmed.length}/${applied.length} fix(es) independently verified; rebuilding`)
  // loop continues -> next Build stage re-runs the objective gate
}

if (!outcome) outcome = { status: 'STALL', reason: `outer iteration cap (${MAX_ITERS}) reached` }

const needsReview = Object.entries(kernelAttempts).filter(([, n]) => n > K).map(([id]) => id)

return {
  status: outcome.status,               // CONVERGED | STALL
  reason: outcome.reason || null,
  iterations: history.length,
  finalTests: outcome.tests || null,
  needsReview,                          // kernels that exhausted budget K
  history,                              // per-iteration: failures, fixes, verdicts, refutations
  progressLog: PROGRESS,
}
