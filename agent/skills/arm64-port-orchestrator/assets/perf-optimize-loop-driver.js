export const meta = {
  name: 'arm64-perf-optimize-loop-driver',
  description: 'Deterministic skeleton for the POST-PORT performance loop: profile the ARM64 build with the profiling skills, decide (in code) whether a hotspot is worth optimizing, hand ONE hotspot to a bounded optimizer agent, independently verify BOTH correctness (negative-control) and a real speedup, re-profile — until no significant hotspot remains, a stall, or the iteration cap. On each accepted optimization, capture the lesson back into the leaf skill tree. Generic: all facts come from args.',
  phases: [
    { title: 'Profile', detail: 'run etl-generator -> perf-sampling-parser -> perf-optimizer; rank hotspots' },
    { title: 'Optimize', detail: 'one optimizer agent per top hotspot, inside a bounded box (task-layer decision)' },
    { title: 'Verify', detail: 'independent agent confirms correctness (negative control) AND a real speedup (decision != verification)' },
    { title: 'Capture', detail: 'route the accepted optimization back into a leaf skill via leaf-skill-creator (lesson feedback)' },
  ],
}

// ============================================================
// DETERMINISTIC ORCHESTRATION LAYER (this is CODE, not an LLM decision).
// The loop, the STOP CONDITION, the retry counters and the convergence/stall
// criteria are hardcoded here. Agents only FILL IN the delegated decisions:
//   ② task-layer   — "how do I optimize this one hotspot" (Optimize)
//   ③ judgement    — "is it still correct AND actually faster" (Verify)
// "Is this hotspot worth optimizing / should we loop again / are we done?" is
// decided by THIS code, from the objective profile numbers — never by an agent.
// ============================================================

// ---- args contract (passed verbatim by the orchestrator skill) -------------
// {
//   projectPath:     string   // absolute root of the ported project
//   runTarget:       string   // path to the built ARM64 program to profile (exe), OR a command
//   runArgs?:        string   // args for the workload (should be a terminating workload)
//   buildCmd:        string   // rebuild the project/target for ARM64 after an edit
//   matchedYaml?:    string   // <report>-matched.yaml — maps hot modules back to porting_items/specs
//   skillsRoot:      string   // path to the easywos-skills skills/ dir (for profiling + leaf-skill-creator)
//   stateDir:        string   // openspec/changes/<change>/ — where state + progress live
//   sourceMap?:      string   // "module=src_path;..." for perf-optimizer Phase 2 (search_source)
//   hotThresholdPct?: number  // default 10 — a leaf below this %CPU self-time is NOT worth optimizing (stop signal)
//   minSpeedupPct?:  number   // default 5  — an optimization must cut the hotspot's own CPU by at least this to be accepted
//   maxIters?:       number   // default 6  — cap on profile->optimize rounds
//   staleStop?:      number   // default 2  — consecutive rounds with the same top hotspot signature and no accepted speedup -> STALL
//   captureLessons?: boolean  // default true — feed each accepted optimization back into a leaf skill
//   syntheticWorkload?: boolean // default false — true if runTarget is a synthetic/test program;
//                               // then lessons are recorded to PERF-PROGRESS.md ONLY, never merged
//                               // into the shared skill tree (a test program is not general evidence)
// }
// Accept args as an object (normal path) or a JSON string (some invocation
// paths deliver it stringified); parse defensively so the driver is robust.
let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
const PROJECT = A.projectPath
const RUN_TARGET = A.runTarget
const RUN_ARGS = A.runArgs || ''
const BUILD_CMD = A.buildCmd
const MATCHED = A.matchedYaml || ''
const SKILLS = A.skillsRoot
const STATE_DIR = A.stateDir
const SOURCE_MAP = A.sourceMap || ''
const HOT_PCT = A.hotThresholdPct ?? 10
const MIN_SPEEDUP = A.minSpeedupPct ?? 5
const MAX_ITERS = A.maxIters || 6
const STALE_STOP = A.staleStop || 2
const CAPTURE = A.captureLessons !== false
const SYNTHETIC = A.syntheticWorkload === true

if (!PROJECT || !RUN_TARGET || !BUILD_CMD || !SKILLS || !STATE_DIR) {
  throw new Error('perf-optimize-loop-driver: missing required args (projectPath, runTarget, buildCmd, skillsRoot, stateDir). The orchestrator resolves these in SKILL.md §8.5 before invoking.')
}

const PROGRESS = `${STATE_DIR}/PERF-PROGRESS.md`

// ---- schemas: force structured returns, validated at the tool layer --------
const PROFILE_SCHEMA = {
  type: 'object',
  required: ['ranSuccessfully', 'totalCpuMs', 'hotspots'],
  properties: {
    ranSuccessfully: { type: 'boolean', description: 'true only if the full profiling pipeline (etl-generator -> perf-sampling-parser -> perf-optimizer analyze) completed and produced a perf_report.json.' },
    totalCpuMs: { type: 'number', description: 'Total CPU ms attributed to the profiled process (from analyze_speedscope.py).' },
    unresolvedPct: { type: 'number', description: 'Percent of samples in unresolved (??) frames. >5 means PDB coverage is weak and rankings are less trustworthy.' },
    speedscopePath: { type: 'string' },
    perfReportPath: { type: 'string' },
    hotspots: {
      type: 'array',
      description: 'Top hot leaves by self%, most-expensive first, from perf-optimizer hot_functions. One entry per distinct hot function.',
      items: {
        type: 'object',
        required: ['frame', 'selfPct'],
        properties: {
          frame: { type: 'string', description: 'e.g. "slowapp!fmaxf" or "module!func".' },
          module: { type: 'string' },
          func: { type: 'string' },
          selfPct: { type: 'number', description: 'Exclusive share of process CPU (%).' },
          selfMs: { type: 'number' },
          suspectModule: { type: 'string', description: 'perf-optimizer suspect_caller_module — the module that should actually be optimized.' },
          kernelId: { type: 'string', description: 'porting_item id if the suspect module maps to a ported kernel (via matchedYaml); enables lesson capture + inner-loop re-entry.' },
        },
      },
    },
  },
}

const OPT_SCHEMA = {
  type: 'object',
  required: ['applied', 'description', 'filesChanged'],
  properties: {
    applied: { type: 'boolean', description: 'true if you applied a concrete optimization to the ROOT-cause code (not a workload/measurement tweak).' },
    description: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    technique: { type: 'string', description: 'Short label of the optimization technique applied (e.g. "scalar-libm -> NEON vminq/vsqrtq + polynomial exp"). Used for lesson capture.' },
    specSkill: { type: 'string', description: 'Which leaf skill/spec this technique belongs to (e.g. sse-avx-to-neon / neon-performance-patterns), if known.' },
    keptScalarFallback: { type: 'boolean', description: 'true if a portable/scalar #else fallback was preserved (required for a NEON specialization).' },
    signature: { type: 'string', description: 'Stable signature of the hotspot addressed (module+func) — used to detect no-progress loops.' },
    note: { type: 'string' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['correct', 'faster', 'reason'],
  properties: {
    correct: { type: 'boolean', description: 'true ONLY if you independently confirmed the optimized code still produces the reference result AND watched a correctness check go RED under a deliberate perturbation then GREEN after revert.' },
    negativeControlObserved: { type: 'boolean', description: 'true if you actually saw the correctness check fail on wrong output. Required true to trust "correct".' },
    faster: { type: 'boolean', description: 'true ONLY if a re-profile / timing you ran yourself shows the hotspot self-time dropped by at least the required minSpeedupPct. Not the optimizer\'s claim — your own measurement.' },
    measuredSpeedupPct: { type: 'number', description: 'The speedup you measured on the hotspot (or whole workload), in percent.' },
    reason: { type: 'string', description: 'What you checked. Default correct=false / faster=false when uncertain.' },
    counterexample: { type: 'string', description: 'If correct=false, the case that breaks it; if faster=false, the numbers that show no real speedup.' },
  },
}

// ---- helpers ---------------------------------------------------------------
function hotSig(h) { return `${(h.module || '')}|${(h.func || h.frame || '')}` }

// ============================================================
// PERF LOOP — deterministic. Every path ends in CONVERGED or STALL(reason).
// CONVERGED here = "no hotspot above the threshold remains" (the STOP CONDITION),
// NOT "we ran out of iterations".
// ============================================================
const history = []
const accepted = []          // optimizations that passed correctness + speedup
let lastTopSig = ''
let staleRounds = 0
let outcome = null

log(`[perf] project=${PROJECT}`)
log(`[perf] run    =${RUN_TARGET} ${RUN_ARGS}`)
log(`[perf] stop condition: no hot leaf >= ${HOT_PCT}% self-CPU; accept speedup >= ${MIN_SPEEDUP}%`)
log(`[perf] append cross-round progress to ${PROGRESS}`)

for (let iter = 1; iter <= MAX_ITERS; iter++) {
  // ---------- Profile stage (objective gate — NOT an agent opinion) --------
  phase('Profile')
  const prof = await agent(
    `Profile the ARM64 build and rank its CPU hotspots. Bash shell available. Working dir: ${PROJECT}.
Use the profiling skills under ${SKILLS}/profiling (do NOT use xperf/WPA):

1. Capture a trace of the target running its workload (REQUIRES an elevated shell; if not elevated, report ranSuccessfully=false with a clear reason):
     python "${SKILLS}/profiling/etl-generator/scripts/collect_etl.py" "${RUN_TARGET}" ${RUN_ARGS ? `--args ${JSON.stringify(RUN_ARGS)}` : ''}
2. Export a SpeedScope flame graph for the target process:
     process_tree.py -> parse_processtree.py (find the target process) -> etl_to_speedscope.py "<name>"
3. Attribute hotspots:
     python "${SKILLS}/profiling/perf-optimizer/scripts/analyze_speedscope.py" "<name>.speedscope.json" --top-n 15

Report the top hot leaves by self% from the perf_report.json hot_functions. For each, include perf-optimizer's suspect_caller_module. ${MATCHED ? `Map the suspect module to a porting_item id using ${MATCHED} and set kernelId when it corresponds to a ported kernel.` : ''}
Do NOT optimize anything — only profile, rank, and report.`,
    { label: `profile#${iter}`, phase: 'Profile', schema: PROFILE_SCHEMA }
  )

  if (!prof || !prof.ranSuccessfully) {
    outcome = { status: 'STALL', reason: `profiling did not complete on iteration ${iter}${prof ? ': ' + (prof.hotspots ? 'no report' : 'ranSuccessfully=false') : ' (agent returned nothing)'}` }
    history.push({ iter, event: 'profile-failed', detail: prof && prof.totalCpuMs })
    break
  }

  const hotspots = (prof.hotspots || []).slice().sort((a, b) => (b.selfPct || 0) - (a.selfPct || 0))
  const top = hotspots[0]
  log(`[iter ${iter}] total=${Math.round(prof.totalCpuMs)}ms  topHot=${top ? `${top.frame} ${top.selfPct.toFixed(1)}%` : 'none'}  unresolved=${(prof.unresolvedPct || 0).toFixed(1)}%`)

  // ---------- Degenerate-profile guard (trust the numbers only if there ARE numbers) ----
  // A trace with almost no CPU, or one where nearly all samples are in
  // unresolved (??) frames, carries no actionable signal — "optimizing" its top
  // leaf means chasing kernel/measurement noise. Require a minimum sampled CPU
  // and resolved coverage before believing any hotspot. This is a STALL (the run
  // could not be profiled meaningfully), NOT a CONVERGED (we did not prove the
  // code is fast — we just failed to measure it). Fix the workload/symbols and retry.
  const MIN_TOTAL_MS = 50
  if ((prof.totalCpuMs || 0) < MIN_TOTAL_MS || (prof.unresolvedPct || 0) >= 90) {
    outcome = { status: 'STALL', reason: `profile has no actionable signal (totalCpuMs=${Math.round(prof.totalCpuMs || 0)} < ${MIN_TOTAL_MS} or unresolved=${(prof.unresolvedPct || 0).toFixed(0)}% >= 90). Use a longer/heavier terminating workload and ensure PDBs resolve the target module; do not optimize noise.` }
    history.push({ iter, event: 'degenerate-profile', totalCpuMs: prof.totalCpuMs, unresolvedPct: prof.unresolvedPct, top: top && { frame: top.frame, selfPct: top.selfPct } })
    break
  }

  // ---------- STOP CONDITION (deterministic, from the numbers) -------------
  // Only application-code leaves are actionable. Unresolved (??) leaves and pure
  // OS/runtime modules are not ours to optimize; excluding them prevents the loop
  // from "optimizing" ntoskrnl/ntdll/kernelbase noise. A hot leaf that is the
  // optimized kernel itself (real work, no scalar-fallback culprit) is expected
  // residual and correctly falls out via the threshold below.
  const SYS_MODULES = new Set(['ntoskrnl','ntdll','kernelbase','kernel32','ucrtbase','vcruntime140','win32u','user32','gdi32','combase','msvcrt','??','?',''])
  const isActionableLeaf = (h) => {
    const m = (h.module || '').toLowerCase()
    const f = (h.frame || '')
    if (SYS_MODULES.has(m)) return false
    if (/[!]\?$|^\?+$/.test(f)) return false   // unresolved "module!?" or "??"
    return true
  }
  const actionable = hotspots.filter(h => (h.selfPct || 0) >= HOT_PCT && isActionableLeaf(h))
  if (actionable.length === 0) {
    const topApp = hotspots.find(isActionableLeaf)
    outcome = { status: 'CONVERGED', iter,
      reason: `no application-code hot leaf at or above ${HOT_PCT}% self-CPU — no significant performance problem remains` +
              (topApp ? ` (hottest app leaf ${topApp.frame} at ${topApp.selfPct.toFixed(1)}%, below threshold)` : ` (all remaining hot leaves are OS/unresolved frames)`),
      totalCpuMs: prof.totalCpuMs }
    history.push({ iter, event: 'converged-no-hotspot', totalCpuMs: prof.totalCpuMs, top: top && { frame: top.frame, selfPct: top.selfPct } })
    break
  }

  // ---------- No-progress guard (deterministic) ----------------------------
  const topSig = actionable.map(hotSig).sort().join(' ;; ')
  if (topSig === lastTopSig) {
    staleRounds++
    if (staleRounds >= STALE_STOP) {
      outcome = { status: 'STALL', reason: `same hotspot(s) survive across ${STALE_STOP + 1} rounds with no accepted speedup: ${topSig}` }
      history.push({ iter, event: 'stale', topSig })
      break
    }
  } else {
    staleRounds = 0
    lastTopSig = topSig
  }

  // Optimize the single most expensive actionable hotspot per round (bounded).
  const target = actionable[0]
  log(`[iter ${iter}] optimizing hotspot: ${target.frame} (${target.selfPct.toFixed(1)}% self, suspect=${target.suspectModule || '?'})`)

  // ---------- ② TASK-LAYER: optimizer agent (bounded box) ------------------
  phase('Optimize')
  const opt = await agent(
    `Optimize ONE performance hotspot in the ARM64 build. Working dir: ${PROJECT}.

HOTSPOT: ${target.frame}  (${target.selfPct.toFixed(1)}% self-CPU, ${Math.round(target.selfMs || 0)}ms)
Suspect module to fix (perf-optimizer): ${target.suspectModule || target.module || 'unknown'}
${target.kernelId ? `This maps to ported kernel: ${target.kernelId}` : ''}
${SOURCE_MAP ? `Source map for locating hot functions: ${SOURCE_MAP}` : ''}

BOX / METHOD:
- Find the hot code in the SUSPECT module's source (perf-optimizer search_source.py can locate it: it flags x64-SIMD-without-NEON files, NEON-blocking compile guards, and per-element scalar libm).
- Apply the RIGHT ARM64 optimization technique for what you find. Consult the leaf skills under ${SKILLS} (sse-avx-to-neon, intrinsics-x64-to-arm64, asm-x64-to-arm64) — e.g. scalar libm (fminf/sqrtf/expf) in a hot loop -> NEON vminq/vmaxq/vsqrtq + a vectorized polynomial for transcendentals; a NEON path gated out by an #ifdef __GNUC__/__ARM_NEON guard -> fix the guard to include _M_ARM64.
- MANDATORY for a SIMD specialization: keep the scalar/portable path as an #else fallback, guard with _M_ARM64 || _M_ARM64EC || __ARM_NEON, handle the n%tail, and add or keep a correctness check comparing the optimized path to the scalar reference.
- Change ONLY the hotspot's owning source; do NOT alter the workload, the timer, or the correctness tolerance to fake a win.

Then rebuild to confirm it compiles: ${BUILD_CMD}

Return structured output; set "signature" to ${JSON.stringify(hotSig(target))}.`,
    { label: `opt:${(target.func || target.frame).split(/[!:]/).pop()}#${iter}`, phase: 'Optimize', schema: OPT_SCHEMA }
  )

  if (!opt || !opt.applied) {
    // Could not optimize this hotspot. If it is the only actionable one, we are stalled.
    history.push({ iter, event: 'no-optimization-applied', hotspot: target.frame, note: opt && opt.note })
    outcome = { status: 'STALL', reason: `no optimization could be applied to the top hotspot ${target.frame}` }
    break
  }

  // ---------- ③ JUDGEMENT-LAYER: independent adversarial verifier ----------
  // The agent that MADE the optimization does NOT bless it. A separate skeptic
  // must (a) confirm correctness with a NEGATIVE CONTROL, and (b) measure a REAL
  // speedup by re-profiling/timing itself. BOTH are required to accept.
  phase('Verify')
  const verdict = await agent(
    `You are an independent adversarial VERIFIER. You did NOT write this optimization. Working dir: ${PROJECT}.

OPTIMIZATION UNDER REVIEW: ${opt.description}
FILES CHANGED: ${(opt.filesChanged || []).join(', ')}
CLAIMED TECHNIQUE: ${opt.technique || 'n/a'}
HOTSPOT TARGETED: ${target.frame} (was ${target.selfPct.toFixed(1)}% self-CPU)

Do BOTH, defaulting every judgement to false when unsure:

(1) CORRECTNESS — mandatory negative control. Build and run the code's own correctness check (the scalar-vs-optimized comparison). Then PERTURB the optimized path (or its reference) so the result MUST diverge, rebuild, and confirm the check reports FAIL / non-zero. Revert and confirm it passes. If it stays green under perturbation, the check is not wired — correct=false.
    Rebuild command: ${BUILD_CMD}

(2) SPEEDUP — measure it yourself. Re-profile with ${SKILLS}/profiling (or time the hotspot workload) and compare the hotspot's self-CPU / the workload's per-unit CPU before vs after. faster=true ONLY if it dropped by at least ${MIN_SPEEDUP}%. Report measuredSpeedupPct. Do NOT trust the optimizer's claim; do NOT accept a speedup obtained by shrinking the workload or loosening tolerance.

Return a verdict. Being wrong here is worse than being skeptical.`,
    { label: `verify:${(target.func || target.frame).split(/[!:]/).pop()}#${iter}`, phase: 'Verify', schema: VERDICT_SCHEMA }
  )

  const ok = verdict && verdict.correct && verdict.faster &&
             (verdict.measuredSpeedupPct == null || verdict.measuredSpeedupPct >= MIN_SPEEDUP)

  history.push({
    iter,
    hotspot: target.frame,
    selfPctBefore: target.selfPct,
    technique: opt.technique,
    applied: true,
    correct: verdict && verdict.correct,
    negativeControl: verdict && verdict.negativeControlObserved,
    faster: verdict && verdict.faster,
    measuredSpeedupPct: verdict && verdict.measuredSpeedupPct,
    accepted: ok,
    reason: verdict && verdict.reason,
    counterexample: verdict && verdict.counterexample,
  })

  if (!ok) {
    // Rejected: correctness or speedup not independently confirmed. Record the
    // dead approach; the no-progress guard will STALL if the same hotspot
    // survives again. (A production driver could revert here; we leave the tree
    // as-is and let the human inspect a refuted optimization.)
    log(`[iter ${iter}] optimization REJECTED (correct=${verdict?.correct} faster=${verdict?.faster}) — recording and continuing`)
    await appendProgress(iter, prof, target, opt, verdict, false)
    continue
  }

  accepted.push({ iter, hotspot: target.frame, technique: opt.technique, specSkill: opt.specSkill, measuredSpeedupPct: verdict.measuredSpeedupPct, description: opt.description, keptScalarFallback: opt.keptScalarFallback })
  log(`[iter ${iter}] optimization ACCEPTED: ${target.frame} -${verdict.measuredSpeedupPct != null ? verdict.measuredSpeedupPct.toFixed(0) + '%' : 'faster'} (${opt.technique})`)

  // ---------- Capture the lesson back into the leaf skill tree -------------
  // Only for an ACCEPTED (correct + measurably faster) optimization, and only
  // when the technique is generalizable (not a one-off workload hack).
  if (CAPTURE) {
    phase('Capture')
    await agent(
      `Capture a VERIFIED ARM64 performance optimization as reusable expert knowledge in the easywos-skills leaf tree. Working dir: ${PROJECT}; skills under ${SKILLS}.

WHAT WAS DONE (independently verified: correct with negative control, and ${verdict.measuredSpeedupPct != null ? verdict.measuredSpeedupPct.toFixed(0) + '%' : 'a real'} speedup):
- Hotspot: ${target.frame} (${target.selfPct.toFixed(1)}% self-CPU before)
- Technique: ${opt.technique}
- Files: ${(opt.filesChanged || []).join(', ')}
- Suggested home skill/spec: ${opt.specSkill || 'choose the best-fitting leaf skill'}

GATE 1 — real vs synthetic. ${SYNTHETIC ? 'This run is flagged as a SYNTHETIC/TEST workload (syntheticWorkload=true). Do NOT merge anything into the shared skill tree — record the lesson only in ' + PROGRESS + ' and STOP. Test programs are not evidence for a general expert rule.' : 'This is a real port. Proceed to GATE 2.'}

GATE 2 — generalizable vs one-off. Decide whether this is GENERALIZABLE (a pattern other ports would hit) or a ONE-OFF (project-specific). If one-off, record it only in ${PROGRESS} and STOP — do not touch the skill tree.

If real AND generalizable:
1. Pick the best-fitting leaf skill (sse-avx-to-neon / intrinsics-x64-to-arm64 / asm-x64-to-arm64 / arm64-inlineasm-to-intrinsics). Prefer EXTENDING an existing spec .md/.yaml over creating a new one; if a genuinely new dimension, use the leaf-skill-creator skill (${SKILLS}/leaf-skill-creator) --add-yaml flow.
2. Add ONE new pattern: a numbered section in the spec .md (x64 construct -> ARM64 replacement, code before/after, pitfalls, and a Validation block that includes the profiler signature — e.g. "hot leaf was module!expf") AND the matching spec entry in the .yaml (unique id, match_rules that fire on BOTH the x86 source construct and the NEON-output self-check, x64_constructs, arm64_constructs, pitfalls, validation_criteria). Keep the exact structure/voice of the existing entries in that file.
3. Regenerate the combined index: node ${SKILLS}/dispatcher-skill/scripts/combine-specs.js
4. Validate the .yaml parses and the new id is present.

Report which skill/spec you extended (or created) and the new pattern's id/name. Do NOT invent a technique that was not actually applied and verified above.`,
      { label: `capture#${iter}`, phase: 'Capture' }
    )
  }

  await appendProgress(iter, prof, target, opt, verdict, true)
  log(`[iter ${iter}] rebuilt + accepted; re-profiling to see if a new hotspot dominates`)
  // loop continues -> next Profile stage re-runs the objective gate
}

if (!outcome) outcome = { status: 'STALL', reason: `perf iteration cap (${MAX_ITERS}) reached with an actionable hotspot still present` }

// State externalization helper (defined as a hoisted function).
async function appendProgress(iter, prof, target, opt, verdict, wasAccepted) {
  await agent(
    `Append one iteration record to the perf-optimize progress log at ${PROGRESS} (create with a header if missing). Append only; do not rewrite prior entries.

## Iteration ${iter}
- Total process CPU: ${Math.round(prof.totalCpuMs)} ms (unresolved ${(prof.unresolvedPct || 0).toFixed(1)}%)
- Hotspot targeted: ${target.frame} — ${target.selfPct.toFixed(1)}% self-CPU (suspect: ${target.suspectModule || target.module || '?'})
- Optimization: ${opt.description} [${opt.technique || 'technique n/a'}]
- Independently verified: correct=${verdict?.correct} (negControl=${verdict?.negativeControlObserved}), faster=${verdict?.faster} (${verdict?.measuredSpeedupPct != null ? verdict.measuredSpeedupPct.toFixed(0) + '%' : 'n/a'})
- Outcome: ${wasAccepted ? 'ACCEPTED' : 'REJECTED — ' + (verdict?.counterexample || verdict?.reason || 'not confirmed')}

This file is read by the archive gate and the final report; be concise and faithful.`,
    { label: `perf-progress#${iter}`, phase: 'Verify' }
  )
}

return {
  status: outcome.status,                    // CONVERGED (stop condition met) | STALL (reason)
  reason: outcome.reason || null,
  iterations: history.length,
  acceptedOptimizations: accepted,           // correct + measurably faster, with technique + speedup
  // Lessons are merged into the shared skill tree only for a REAL port; a
  // synthetic/test workload's wins stay in PERF-PROGRESS.md (see Capture GATE 1).
  lessonsCaptured: (CAPTURE && !SYNTHETIC) ? accepted.filter(a => a.specSkill).map(a => ({ hotspot: a.hotspot, skill: a.specSkill, technique: a.technique })) : [],
  syntheticWorkload: SYNTHETIC,
  finalTotalCpuMs: outcome.totalCpuMs || null,
  history,                                   // per-iteration: hotspot, technique, verdict, accept/reject
  progressLog: PROGRESS,
}
