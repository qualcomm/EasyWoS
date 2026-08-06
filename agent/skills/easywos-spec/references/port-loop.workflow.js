export const meta = {
  name: 'easywos-port-loop',
  description: 'Generic easywos verify→retry porting loop: drive any x64→ARM64 matched-YAML project through dispatch → build → gtest + negative-control → feedback retry ≤K, until every porting_item passes or is exhausted to review.',
  phases: [
    { title: 'Load',   detail: 'read matched YAML → item list' },
    { title: 'Port',   detail: 'dispatcher per needs-work item (parallel; --feedback on retry)' },
    { title: 'Build',  detail: 'build the ARM64 test binary/binaries (barrier if shared)' },
    { title: 'Verify', detail: 'negative-control gate + gtest run → per-item verdicts' },
  ],
}

// ── Configuration via args (NO project-specific literals in this script) ─────
// Invoke with, e.g.:
//   Workflow({ scriptPath: '.../port-loop.workflow.js', args: {
//     matchedYaml: 'x265/x265-arm64-porting-report-matched.yaml',
//     verifyDir:   'x265/arm64-verify',
//     buildCmd:    'x265/arm64-verify/build_and_compare.bat',   // build+test driver
//     retryBudget: 3,
//     sharedBinary: true,       // one test binary for all items → build is a barrier
//     dryRun: false,            // true = print commands, mutate nothing
//     only: ['pixel-sad'],      // optional: restrict to a subset of item ids
//   }})
// args may arrive as an object or as a JSON-encoded string, depending on how
// the workflow is invoked; normalize to an object either way.
let cfg = args ?? {}
if (typeof cfg === 'string') { try { cfg = JSON.parse(cfg) } catch { cfg = {} } }
const MATCHED_YAML  = cfg.matchedYaml
const VERIFY_DIR    = cfg.verifyDir  ?? null
const BUILD_CMD     = cfg.buildCmd   ?? (VERIFY_DIR ? `${VERIFY_DIR}/build_and_compare.bat` : null)
const FEEDBACK_DIR  = cfg.feedbackDir ?? (VERIFY_DIR ? `${VERIFY_DIR}/feedback` : 'feedback')
const K             = cfg.retryBudget ?? 3
const SHARED_BINARY = cfg.sharedBinary ?? true    // conservative default: assume one shared binary → build barrier
const DRY_RUN       = cfg.dryRun ?? false
const ONLY          = Array.isArray(cfg.only) ? cfg.only : null

if (!MATCHED_YAML) {
  log('ERROR: args.matchedYaml is required (path to the <scan>-matched.yaml). Nothing to drive.')
  return { error: 'missing args.matchedYaml' }
}
if (!BUILD_CMD && !DRY_RUN) {
  log('ERROR: need args.buildCmd or args.verifyDir to build/verify (or set args.dryRun:true).')
  return { error: 'missing build command' }
}
log(`Config: matched=${MATCHED_YAML} verifyDir=${VERIFY_DIR} K=${K} sharedBinary=${SHARED_BINARY} dryRun=${DRY_RUN}${ONLY ? ` only=[${ONLY.join(',')}]` : ''}`)

// ── Structured-output schemas ──────────────────────────────────────────────
const ITEMS_SCHEMA = {
  type: 'object', required: ['items'],
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object', required: ['id', 'specs', 'confidence'],
        properties: {
          id:         { type: 'string' },
          specs:      { type: 'array', items: { type: 'integer' } }, // [] => freeform
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
      },
    },
  },
}
const PORT_SCHEMA = {
  type: 'object', required: ['id', 'emitted'],
  properties: {
    id:      { type: 'string' },
    emitted: { type: 'boolean' },
    outputs: { type: 'array', items: { type: 'string' } },
    note:    { type: 'string' },
  },
}
const BUILD_SCHEMA = {
  type: 'object', required: ['ok'],
  properties: {
    ok:     { type: 'boolean' },
    errors: {
      type: 'array',
      items: {
        type: 'object', required: ['item_id', 'failure_kind', 'detail'],
        properties: {
          item_id:      { type: 'string' },
          failure_kind: { type: 'string', enum: ['compile_error', 'link_error'] },
          detail:       { type: 'string' },
        },
      },
    },
    raw: { type: 'string' },
  },
}
const VERIFY_SCHEMA = {
  type: 'object', required: ['negative_control_passed', 'results'],
  properties: {
    negative_control_passed: { type: 'boolean' },        // V.0: global perturbation turned suite red
    dead_fixtures: { type: 'array', items: { type: 'string' } },
    results: {
      type: 'array',
      items: {
        type: 'object', required: ['item_id', 'passed'],
        properties: {
          item_id:          { type: 'string' },
          passed:           { type: 'boolean' },
          shown_red_at_v0:  { type: 'boolean' },
          failing_fixtures: { type: 'array', items: { type: 'string' } },
          failure_kind:     { type: 'string', enum: ['assertion', 'crash', 'timeout', ''] },
          detail:           { type: 'string' },
          hypothesis:       { type: 'string' },
        },
      },
    },
  },
}

// ── Phase: Load ─────────────────────────────────────────────────────────────
phase('Load')
const loaded = await agent(
  `Read ${MATCHED_YAML} (relative to cwd = repo root). It is an EasyWoS
   x64-to-arm64-porting matched YAML. For every entry under porting_items,
   return {id, specs, confidence} where specs = its port_spec_ids array ([] for
   freeform) and confidence = match_confidence.llm_confidence. Return ONLY that
   list — port nothing.`,
  { label: 'load:matched-yaml', phase: 'Load', schema: ITEMS_SCHEMA }
)
let allItems = loaded?.items ?? []
if (ONLY) allItems = allItems.filter(i => ONLY.includes(i.id))
if (allItems.length === 0) {
  log('No porting_items to drive (empty matched YAML or `only` filtered all out).')
  return { error: 'no items', matched: MATCHED_YAML }
}
log(`Loaded ${allItems.length} item(s): ${allItems.map(i => i.id).join(', ')}`)

// ── Loop state ───────────────────────────────────────────────────────────────
const state = {}
for (const it of allItems) state[it.id] = { item: it, attempt: 0, done: false, review: false, lastFeedback: null }
const needsWork = () => allItems.map(i => state[i.id]).filter(s => !s.done && !s.review)

const dispatchCmd = (s) => {
  const specsPart = s.item.specs.length ? `--specs ${s.item.specs.join(',')}` : `--mode llm-freeform`
  const fb = s.lastFeedback ? ` --feedback ${s.lastFeedback}` : ''
  return `/dispatcher-skill ${s.item.id} ${specsPart} --source ${MATCHED_YAML}${fb}`
}

// ── Dry run: show the loop mechanics without touching the tree ───────────────
if (DRY_RUN) {
  log('DRY RUN — no source is modified, no build is run. First-attempt dispatch commands:')
  for (const s of needsWork()) log(`  ${dispatchCmd(s)}`)
  log(`Build barrier each round: ${BUILD_CMD || '(none configured)'}`)
  log(`On failure → write ${FEEDBACK_DIR}/<id>.attemptN.yaml, re-dispatch with --feedback, up to K=${K}, else [NEEDS REVIEW].`)
  return { dryRun: true, items: allItems.map(i => i.id), buildCmd: BUILD_CMD, retry_budget: K }
}

// ── Round loop: Port (parallel) → Build (barrier) → Verify (barrier) ─────────
// A single shared test binary forces a build barrier every round (round-loop).
// If sharedBinary:false and per-item binaries exist, build/verify could run
// per-item concurrently (easywos-spec §8.4); we keep the round-loop here because
// it is correct for both and simplest to reason about.
let round = 0
while (needsWork().length > 0) {
  round++
  const batch = needsWork()
  log(`── Round ${round}: ${batch.length} item(s) need work: ${batch.map(s => s.item.id).join(', ')}`)

  // Port — parallel; porting is genuinely independent per item.
  phase('Port')
  const ported = await parallel(batch.map((s) => async () => {
    s.attempt++
    const retryTag = s.attempt > 1 ? ` [ATTEMPT ${s.attempt}/${K}]` : ''
    return agent(
      `Execute ONE attempt of the easywos porting loop for item "${s.item.id}"${retryTag}. cwd = repo root.

       Run the dispatcher exactly as specified, then ensure the leaf-skill output
       is written into the source tree AND that this item has a gtest fixture in
       the verify project${VERIFY_DIR ? ` under ${VERIFY_DIR}` : ''}:

         ${dispatchCmd(s)}

       ${s.lastFeedback
         ? `RETRY: load feedback ${s.lastFeedback} (dispatcher §2.7) — prior failing
            fixtures / compiler output / hypothesis. Your new output MUST NOT
            reproduce the failed construct; if the same failure_kind recurs, change
            approach rather than repeating the fix.`
         : `First attempt — no prior feedback.`}

       Return {id, emitted, outputs, note}. Do NOT build or run tests.`,
      { label: `port:${s.item.id}`, phase: 'Port', schema: PORT_SCHEMA }
    )
  }))
  const portFail = ported.filter(Boolean).filter(p => !p.emitted)
  if (portFail.length) log(`Port: ${portFail.length} item(s) emitted nothing: ${portFail.map(p => p.id).join(', ')}`)

  // Build — barrier (shared binary).
  phase('Build')
  const build = await agent(
    `cwd = repo root. Configure and build the ARM64 unit-test binary via the
     project's driver (BUILD step only — do NOT run tests here):

       ${BUILD_CMD}

     If the build FAILS, parse compiler/linker output and attribute each error to
     the porting_item whose kernel or fixture caused it (ids: ${allItems.map(i => i.id).join(', ')}).
     Return {ok, errors:[{item_id, failure_kind, detail}], raw}. On success:
     ok:true, empty errors.`,
    { label: `build:round${round}`, phase: 'Build', schema: BUILD_SCHEMA }
  )

  if (!build || !build.ok) {
    const errs = build?.errors ?? []
    log(`Build FAILED — ${errs.length} error(s) attributed.`)
    for (const e of errs) {
      const s = state[e.item_id]; if (!s) continue
      const fbPath = `${FEEDBACK_DIR}/${e.item_id}.attempt${s.attempt + 1}.yaml`
      await agent(
        `cwd = repo root. Write/append a dispatcher §2.7.1 feedback YAML to ${fbPath}
         for "${e.item_id}". attempt: ${s.attempt + 1}; append prior_attempts entry
         {stage: build, failure_kind: ${e.failure_kind}, detail (verbatim, truncated): |
${e.detail}
}; add a hypothesis if diagnosable. Preserve earlier attempts. Return the path only.`,
        { label: `feedback:${e.item_id}`, phase: 'Build', schema: { type: 'object', required: ['path'], properties: { path: { type: 'string' } } } }
      )
      s.lastFeedback = fbPath
      if (s.attempt >= K) { s.review = true; log(`  ${e.item_id}: K=${K} exhausted → [NEEDS REVIEW]`) }
    }
    if (errs.length === 0) { log('Build failed with no attributable errors — stopping to avoid a hung loop (dispatcher §5.4).'); break }
    continue
  }

  // Verify — V.0 negative-control gate then V.5 real run. Barrier.
  phase('Verify')
  const verify = await agent(
    `cwd = repo root. The ARM64 test binary is built. Apply easywos-spec §7.6
     negative-control gate BEFORE trusting any pass:

     1) V.0 batch negative control: in a throwaway/perturbed build, corrupt every
        fixture's expected reference (e.g. +1 on each reference). Run the suite —
        it MUST go entirely red. Any fixture that stays green under global
        perturbation is a DEAD check (identity stub / self-compare / kernel not
        linked) → record in dead_fixtures. Then REVERT and rebuild clean.
     2) V.5 real run: run the test step clean (${BUILD_CMD} runs tests after build,
        or invoke the built test binary). Map each gtest fixture to its
        porting_item id (ids: ${allItems.map(i => i.id).join(', ')}).

     Per item return {item_id, passed, shown_red_at_v0, failing_fixtures,
     failure_kind, detail, hypothesis}. passed:true ONLY if green AND observed red
     at V.0 (never-red = unverified, NOT passing). Also return
     negative_control_passed (true iff no dead_fixtures) and dead_fixtures.`,
    { label: `verify:round${round}`, phase: 'Verify', schema: VERIFY_SCHEMA }
  )

  const byId = {}
  for (const r of (verify?.results ?? [])) byId[r.item_id] = r

  for (const s of batch) {
    const r = byId[s.item.id]
    if (r && r.passed && r.shown_red_at_v0) { s.done = true; log(`  ✔ ${s.item.id}: green & shown-red → done`); continue }
    const reason = !r ? 'no verify result'
      : (!r.shown_red_at_v0 && r.passed) ? 'passed but NEVER shown red (unverified/dead check)'
      : `test failed (${(r.failing_fixtures || []).join(', ') || r.failure_kind || 'unknown'})`
    if (s.attempt >= K) { s.review = true; log(`  ⚠ ${s.item.id}: ${reason}; K=${K} exhausted → [NEEDS REVIEW]`); continue }
    const fbPath = `${FEEDBACK_DIR}/${s.item.id}.attempt${s.attempt + 1}.yaml`
    await agent(
      `cwd = repo root. Write/append a dispatcher §2.7.1 feedback YAML to ${fbPath}
       for "${s.item.id}". attempt: ${s.attempt + 1}; append prior_attempts entry
       {stage: test, failure_kind: ${r?.failure_kind || 'assertion'}, failing_fixtures:
       ${JSON.stringify(r?.failing_fixtures || [])}, detail (verbatim, truncated): |
${(r?.detail || reason)}
, hypothesis: ${JSON.stringify(r?.hypothesis || '')}}. Preserve earlier attempts. Return the path only.`,
      { label: `feedback:${s.item.id}`, phase: 'Verify', schema: { type: 'object', required: ['path'], properties: { path: { type: 'string' } } } }
    )
    s.lastFeedback = fbPath
    log(`  ↺ ${s.item.id}: ${reason} → feedback written, retry ${s.attempt + 1}/${K}`)
  }

  if (verify && verify.negative_control_passed === false)
    log(`⚠ Negative-control gate FAILED — dead fixtures: ${(verify.dead_fixtures || []).join(', ')}. Their items are unverified, not passing.`)
}

// ── Terminal report ──────────────────────────────────────────────────────────
const done   = allItems.filter(i => state[i.id].done).map(i => i.id)
const review = allItems.filter(i => state[i.id].review).map(i => i.id)
log(`Loop terminated after ${round} round(s). Passed ${done.length}/${allItems.length}. NEEDS REVIEW ${review.length}.`)
return {
  rounds: round,
  retry_budget: K,
  passed: done,
  needs_review: review.map(id => ({ id, last_feedback: state[id].lastFeedback })),
  matched_yaml: MATCHED_YAML,
}
