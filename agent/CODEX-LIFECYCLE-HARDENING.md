# EasyWoS Codex 生命周期补强设计

> 状态：核心方案已实施（Codex 生命周期、dispatcher 证据链、matcher、性能终态与 archive gate）
> 目标插件：EasyWoS
> 适用宿主：Codex，兼顾 Claude Code/QGenie 现有流程
> 实现入口位于 `scripts/codex/`；本文同时保留设计依据、实施顺序和验收标准。

## 1. 背景与结论

EasyWoS 当前已经描述了较完整的 x64→ARM64 流程，包括扫描、规格匹配、叶子技能迁移、独立验证、全项目构建测试、性能分析和 OpenSpec 归档。但这些约束主要存在于 `SKILL.md` 和 Workflow scriptlet 中。

Claude Code 可以通过 Workflow 运行时执行 `outer-loop-driver.js` 和 `perf-optimize-loop-driver.js`；Codex 没有相同的 Workflow 注入环境，也没有原生 slash-command 运行时。因此，在 Codex 中“按文档人工执行等价流程”时，关键步骤可能被遗漏、顺序可能漂移，最终也缺少一个不可绕过的机器门禁。

此前移植暴露出的缺口不是 ARM64 技术能力不足，而是生命周期执行层不够确定：

| 缺口 | 直接表现 | 根因 | 本方案的处理 |
|---|---|---|---|
| Codex 无法执行现有 Workflow scriptlet | 流程依赖模型按文字复现 | 插件缺少 Codex 可运行的确定性驱动器 | 增加 Codex CLI 适配层和持久化状态机 |
| dispatcher 调用不可审计 | 能说明“用了某技能”，但没有完整调用记录 | dispatcher 目前主要是文字协议 | 增加可执行 dispatcher adapter 和 dispatch record |
| matcher 漏配 `_mm_movemask_epi8` | 某些应该命中的规则未进入候选集 | 一行只有单一 scope，规则表达能力不足 | 一行多 scope、组合条件、逐条匹配证据 |
| x86 `"=r"` 被误判为 ARM64 inline asm | 无关 ARM64 规格进入候选集 | 单个弱特征即可命中，缺少上下文约束 | `all_of`/`any_of`/`none_of` 组合规则 |
| 性能阶段未真正执行仍可结束 | 无 ETL、SpeedScope 或 `PERF-PROGRESS.md` | 性能状态没有被归档门禁统一检查 | 标准化性能终态和强制证据 |
| OpenSpec 提前归档 | 正确性绿色被当作完整生命周期绿色 | 归档条件分散在自然语言中 | 新增不可绕过的 `archive-gate.js` |
| producer/verifier 分离不可证明 | 同一个上下文可能既修改又验收 | 没有身份和会话证据 | 记录不同 session ID 和产物哈希 |

## 2. 设计目标

本次改造应实现以下结果：

1. Codex 能用普通 Node CLI 驱动完整流程，不依赖 Claude Workflow 注入变量。
2. 每个生命周期阶段都有确定状态、输入、输出、证据和允许的后继状态。
3. matcher、dispatcher、构建、测试、负向控制、性能分析和归档都留下机器可校验的记录。
4. 缺少任何必需证据时，归档命令必须失败，而不是仅输出提醒。
5. 中断后可从状态文件恢复，不能依赖聊天上下文记忆。
6. 保留现有 Claude Code/QGenie 使用方式；Codex 适配层是新增实现，不删除现有 Workflow 资产。
7. matcher 或 leaf spec 出现缺口时，能够完成“失败回归测试→修规则→重建 combined specs→重新匹配→重新 dispatch”的闭环。

## 3. 非目标

- 不在本次补强中重写所有 ARM64 leaf skill。
- 不把性能优化本身硬编码进生命周期驱动器；驱动器只负责调度、状态和证据。
- 不让脚本代替模型完成需要语义判断的移植工作。
- 不直接修改插件缓存目录或 `~/.agents/skills` 中的安装副本。
- 不通过手工编辑 marketplace 文件完成插件更新。

## 4. 建议目录结构

在 EasyWoS 插件源码中新增：

```text
scripts/
└── codex/
    ├── lifecycle-driver.js
    ├── dispatcher-adapter.js
    ├── archive-gate.js
    ├── evidence-validator.js
    └── schemas/
        ├── lifecycle-state.schema.json
        ├── dispatch-record.schema.json
        ├── command-evidence.schema.json
        └── performance-evidence.schema.json

tests/
├── codex-lifecycle/
│   ├── lifecycle-driver.test.js
│   ├── dispatcher-adapter.test.js
│   ├── archive-gate.test.js
│   └── fixtures/
└── matcher/
    ├── multi-scope.test.js
    └── compound-rules.test.js
```

每个被移植项目的 OpenSpec change 目录保存运行态证据：

```text
openspec/changes/<change>/
├── LIFECYCLE-STATE.yaml
├── dispatch/
│   ├── <porting-item>.request.yaml
│   └── <porting-item>.result.yaml
├── evidence/
│   ├── matcher.json
│   ├── build-x64.json
│   ├── test-x64.json
│   ├── build-arm64.json
│   ├── test-arm64.json
│   ├── negative-control.json
│   └── verifier.json
├── perf/
│   ├── baseline.etl
│   ├── baseline.speedscope.json
│   ├── optimized.etl
│   ├── optimized.speedscope.json
│   ├── paired-benchmark.json
│   └── checksums.json
├── OUTER-PROGRESS.md
└── PERF-PROGRESS.md
```

## 5. 确定性生命周期状态机

### 5.1 主阶段

`LIFECYCLE-STATE.yaml` 中的 `phase` 只能按下列方向推进：

```text
PREFLIGHT
  → SCAN
  → MATCH
  → REFINE
  → DISPATCH
  → INTEGRATE
  → BUILD
  → TEST
  → NEGATIVE_CONTROL
  → PROFILE
  → VERIFY
  → ARCHIVE_READY
  → ARCHIVED
```

任何阶段失败时保留当前 `phase`，并将 `run_status` 设置为 `PAUSED`、`STALLED` 或 `FAILED`。恢复执行必须显式读取现有状态和证据，不允许仅通过 `--resume-from` 跳过未验证阶段。

### 5.2 运行状态

```yaml
run_status: ACTIVE | PAUSED | STALLED | FAILED | COMPLETE
```

- `ACTIVE`：当前仍可自动推进。
- `PAUSED`：需要外部条件，例如管理员权限或用户提供可终止 workload。
- `STALLED`：已实际执行，但达到重试上限或无可接受改进。
- `FAILED`：证据损坏、命令失败或状态迁移非法。
- `COMPLETE`：仅允许与 `phase: ARCHIVED` 同时出现。

### 5.3 状态文件示例

```yaml
schema_version: 1
change_id: fastvalidate-utf8-arm64
project_root: C:/work/fastvalidate-utf-8-arm64
target: arm64-windows
phase: TEST
run_status: ACTIVE
created_at: 2026-10-08T10:00:00+08:00
updated_at: 2026-10-08T11:15:00+08:00

inputs:
  scan_report: easywos-report.yaml
  matched_yaml: easywos-matched.yaml
  openspec_tasks: tasks.md

phases:
  match:
    status: PASSED
    evidence: evidence/matcher.json
    sha256: <sha256>
  dispatch:
    status: PASSED
    expected_items: [utf8-validate]
    completed_items: [utf8-validate]
  build:
    x64: PASSED
    arm64: PASSED
  test:
    x64: PASSED
    arm64: PASSED
  negative_control:
    status: PENDING
  performance:
    status: NOT_STARTED
  verification:
    status: PENDING
  archive:
    status: BLOCKED

history:
  - from: BUILD
    to: TEST
    at: 2026-10-08T11:15:00+08:00
    evidence_sha256: <sha256>
```

### 5.4 状态迁移规则

`lifecycle-driver.js` 负责：

- 初始化和校验 `LIFECYCLE-STATE.yaml`。
- 根据当前阶段输出下一步所需动作及必需输入。
- 在阶段提交时调用 `evidence-validator.js`。
- 只在证据完整且哈希匹配时推进状态。
- 拒绝倒退、跨阶段跳转和覆盖已有成功证据。
- 允许 `--retry-current` 重试当前失败阶段，并追加 history。
- 允许 `--invalidate-from <phase>` 主动使某阶段及其下游证据失效；matcher/spec 或源码改变后必须使用该机制。

建议 CLI：

```text
node scripts/codex/lifecycle-driver.js init --change <dir> --project <dir>
node scripts/codex/lifecycle-driver.js next --change <dir>
node scripts/codex/lifecycle-driver.js submit --change <dir> --phase MATCH --evidence <file>
node scripts/codex/lifecycle-driver.js retry-current --change <dir>
node scripts/codex/lifecycle-driver.js invalidate-from --change <dir> --phase MATCH --reason <text>
```

## 6. Codex dispatcher 适配

### 6.1 问题

当前 `dispatcher-skill` 主要定义了模型应如何组装上下文并路由 leaf skill，但没有可执行入口生成稳定的请求、结果和审计记录。Codex 中自然语言调用成功并不等于可以证明传入了正确的 matcher 结果、spec 内容、feedback 和 source range。

### 6.2 适配器职责

新增 `scripts/codex/dispatcher-adapter.js`，分为两个明确动作：

1. `prepare`：读取 matched YAML，验证 porting item 和 spec ID，解析 leaf skill，生成不可变 request。
2. `record-result`：在 Codex 完成对应 leaf skill 工作后，记录结果文件、producer session、patch hash、测试入口和 feedback 链。

适配器不假装“在 Node 中直接调用 Codex skill”。它负责把 dispatcher 的文字协议变成宿主可执行、可恢复、可审计的交接协议；Codex 负责实际使用 request 指定的 leaf skill完成迁移。

### 6.3 Dispatch request

```yaml
schema_version: 1
dispatch_id: utf8-validate-attempt-1
porting_item_id: utf8-validate
source_matched_yaml: easywos-matched.yaml
source_matched_yaml_sha256: <sha256>
mode: spec-driven
primary_leaf_skill: intrinsics-x64-to-arm64
supplemental_leaf_skills:
  - arm64-baseline-porting
port_spec_ids: [97, 146, 151, 152]
matched_evidence_ids:
  - match-97-1
  - match-146-1
source_ranges:
  - src/validate.cpp:42-96
feedback_files: []
attempt: 1
prepared_at: <timestamp>
```

### 6.4 Dispatch result

```yaml
schema_version: 1
dispatch_id: utf8-validate-attempt-1
status: APPLIED | NEEDS_RETRY | FAILED
producer:
  harness: codex
  session_id: <producer-session-id>
leaf_skills_used:
  - intrinsics-x64-to-arm64
files_changed:
  - path: src/validate.cpp
    sha256_before: <sha256>
    sha256_after: <sha256>
patch_sha256: <sha256>
feedback_consumed: []
verification_required: true
recorded_at: <timestamp>
```

### 6.5 强制规则

- `port_spec_ids` 必须能追溯到真实 matcher 输出，禁止手填无法验证的 ID。
- request 中每个 spec ID 必须存在于当前 `combined-spec-summary.yaml`。
- request 中保存 matched YAML 哈希；matcher 重跑后旧 request 自动失效。
- result 的 producer session 不能为空。
- 每个 porting item 必须存在 request 和 result；缺一项即不能进入 `INTEGRATE`。
- retry 必须引用前一次 feedback，不能覆盖旧记录。

## 7. Matcher 修复

### 7.1 一行多 scope

把当前单值 `classifyLine(line)` 改为返回 scope 集合，例如：

```text
_mm_movemask_epi8(v)
→ [expression, intrinsic_call, function_call]
```

匹配时，只要规则 scope 与行的 scope 集合有交集即可进入候选。保留当前 scope 名称和兼容映射，避免破坏已有 spec。

这项修复用于避免一行同时具备“表达式、intrinsic 调用、函数调用”等属性时，只因优先分类落入一个 scope 而漏配。

### 7.2 组合匹配条件

为 `metadata.match_rules` 增加向后兼容的组合结构：

```yaml
match_groups:
  - id: arm64-inline-asm-block
    all_of:
      - pattern: 'asm\\s*(volatile)?\\s*\\('
        type: regex
        scope: inline_asm
      - pattern: '\\b(v[0-9]+|x[0-9]+|w[0-9]+)\\b'
        type: regex
        scope: instruction
    any_of:
      - pattern: '\\b(pmull|ld1|st1|tbl|ext)\\b'
        type: regex
        scope: instruction
      - pattern: '__aarch64__|_M_ARM64|_M_ARM64EC'
        type: regex
        scope: preprocessor
    none_of:
      - pattern: '__x86_64__|_M_X64'
        type: regex
        scope: preprocessor
```

旧的平铺 `match_rules` 继续按 `any_of` 处理。涉及 inline asm 方言、ABI 或架构判断的高风险 spec 应逐步迁移到组合规则，禁止仅凭 `"=r"` 之类跨架构共有约束判定为 ARM64 asm。

### 7.3 具体匹配证据

matcher 输出不能只列 spec ID 和 pattern，还要给出：

```json
{
  "evidence_id": "match-146-1",
  "spec_id": 146,
  "rule_id": "movemask-intrinsic",
  "file": "src/validate.cpp",
  "line": 61,
  "scopes": ["expression", "intrinsic_call"],
  "pattern": "_mm_movemask_epi8",
  "excerpt": "const int mask = _mm_movemask_epi8(v);"
}
```

多段 `code_range` 必须保留原文件和行号映射；不能只对拼接后的 context 给出无来源行号。

### 7.4 回归测试

至少加入以下红→绿用例：

1. `_mm_movemask_epi8` 在赋值表达式中仍命中 intrinsic spec。
2. x86 asm block 中的 `"=r"` 不命中 ARM64 inline-asm spec。
3. 带 `__aarch64__` guard 和 ARM64 指令的 asm block 正确命中。
4. 一行多个 intrinsic 调用时，所有适用 spec 都有证据。
5. 多段 source range 的证据行号仍指向原文件。
6. 现有 matcher golden tests 不退化。

## 8. Spec 回灌闭环

当移植或性能验证发现 matcher/spec 缺口时，必须按以下顺序执行：

```text
创建失败回归用例
  → 修 matcher 或 leaf spec
  → node skills/dispatcher-skill/scripts/combine-specs.js
  → matcher 单元测试变绿
  → 对原项目重新运行 matcher
  → 确认新 spec 出现在具体证据中
  → lifecycle invalidate-from MATCH
  → 重新生成 dispatch request
  → 重新移植、构建、测试和验证
```

仅修改 leaf YAML、但未重建 `combined-spec-summary.yaml`，状态应记为 `DORMANT_SPEC_CHANGE`，archive gate 必须拒绝归档。

## 9. 构建、测试和负向控制证据

每条命令保存结构化证据，而不是只在 Markdown 中写“已通过”：

```json
{
  "schema_version": 1,
  "stage": "test-arm64",
  "command": "ctest --test-dir build-arm64 --output-on-failure",
  "working_directory": "C:/work/project",
  "started_at": "<timestamp>",
  "finished_at": "<timestamp>",
  "exit_code": 0,
  "tests_discovered": 42,
  "tests_passed": 42,
  "tests_failed": 0,
  "stdout_sha256": "<sha256>",
  "stderr_sha256": "<sha256>",
  "binary_sha256": "<sha256>",
  "source_tree_fingerprint": "<sha256>"
}
```

最低要求：

- x64 基线构建和项目测试通过。
- ARM64 全项目构建和项目测试通过。
- 测试数不能为 0；0 tests 是 wiring failure。
- 构建和测试证据必须对应同一源码指纹。
- 负向控制必须记录 deliberate perturbation、预期失败、实际非零退出、恢复后的绿色结果。
- archive gate 校验负向控制的红、恢复和最终绿三个阶段，而不是只检查一个布尔字段。

## 10. Producer 与 Verifier 分离

每个修改必须由独立 verifier 验收。证据格式至少包含：

```yaml
producer_session_id: <id-a>
verifier_session_id: <id-b>
producer_patch_sha256: <sha256>
verifier_observed_patch_sha256: <same-sha256>
negative_control:
  introduced_by_session: <id-b>
  red_exit_code: 1
  restored_green_exit_code: 0
verdict: VERIFIED | REFUTED
```

规则：

- producer 和 verifier session ID 必须不同。
- verifier 必须验证与 producer 相同的 patch hash。
- 测试修复只有在 verifier 亲自观察到负向控制变红、恢复后变绿时才能标为 `VERIFIED`。
- 无法创建独立 session 时必须标为 `UNVERIFIED`，不得伪装成完整生命周期成功。

## 11. 性能阶段

### 11.1 性能终态

性能阶段只允许三个可归档终态：

```text
CONVERGED
STALLED
SKIPPED_BY_USER
```

- `CONVERGED`：已实际 profiling，且没有超过阈值的可行动热点，或优化后达到收敛条件。
- `STALLED`：已实际 profiling，但达到迭代上限、热点无可接受方案或无独立确认的加速。必须保留真实 profiler 证据和 blocker。
- `SKIPPED_BY_USER`：用户显式传入 `--no-profile`；必须记录原始参数或用户授权证据。

以下状态不可归档：

- `NOT_STARTED`
- `RUNNING`
- `PAUSED_NEEDS_ADMIN`
- `NO_WORKLOAD`
- `PROFILE_FAILED`

`STALLED` 与“没有运行”不同：只有至少成功产生一份有效 ETL/SpeedScope，并完成热点解析，才允许使用该终态。

### 11.2 标准性能产物

```text
PERF-PROGRESS.md
perf/baseline.etl
perf/baseline.speedscope.json
perf/optimized.etl                 # 发生优化时必需
perf/optimized.speedscope.json     # 发生优化时必需
perf/paired-benchmark.json         # 比较前后性能时必需
perf/checksums.json
```

`paired-benchmark.json` 应保存 A/B 交替次序、每轮耗时、warmup、统计量和最小接受加速阈值。`checksums.json` 证明 baseline 与 optimized 完成相同工作。

### 11.3 `PERF-PROGRESS.md` 最低内容

- workload 命令、持续时间和是否为 synthetic workload。
- ETL 和 SpeedScope 路径及哈希。
- 目标进程选择依据。
- Top-N hotspot、self CPU 和 unresolved symbol 比例。
- 每次优化的 producer/verifier、正确性负向控制和独立重测结果。
- 捕获到 leaf spec 的经验，或未回灌的明确原因。
- 最终性能状态及 blocker。

## 12. 不可绕过的 Archive Gate

新增 `scripts/codex/archive-gate.js`。仅在 Codex 分支中，OpenSpec archive 前必须先运行它，且 OpenSpec tasks 的最后一项必须调用该脚本。Claude Code 保留原有 Workflow driver、`.orchestrator-state.yaml` 和 `opsx:archive` 流程，不调用 `scripts/codex/*`，也不要求 `LIFECYCLE-STATE.yaml`。

建议命令：

```text
node scripts/codex/archive-gate.js --change openspec/changes/<change> --strict
```

### 12.1 必查项

archive gate 必须检查：

1. `LIFECYCLE-STATE.yaml` schema 合法，当前 phase 为 `ARCHIVE_READY`。
2. matcher 证据来自真实 `spec_matcher.js` 执行，输入、combined specs 和输出哈希一致。
3. 每个 porting item 都有完整 dispatch request/result。
4. dispatch 的 spec ID 与 matcher 证据一一对应。
5. x64 和 ARM64 全项目构建通过。
6. x64 和 ARM64 项目测试通过且 tests discovered 大于 0。
7. 必需测试已完成红→绿负向控制。
8. producer/verifier session 不同，且 verifier 验证的是同一个 patch hash。
9. 性能状态是 `CONVERGED`、真实执行后的 `STALLED` 或用户显式 `SKIPPED_BY_USER`。
10. `PERF-PROGRESS.md` 与性能二进制产物匹配。
11. matcher/spec 有修改时，combined specs 已重建并对原项目重匹配。
12. `openspec validate --strict` 成功。
13. 所有记录引用的文件存在，SHA-256 一致，源码指纹没有过期。

### 12.2 失败行为

- 任一检查失败时返回非零退出码。
- 输出稳定的错误代码，例如 `E_MATCHER_EVIDENCE_MISSING`、`E_PERF_NOT_TERMINAL`、`E_VERIFIER_NOT_INDEPENDENT`。
- 不自动修复或伪造证据。
- 不调用 OpenSpec archive。
- 将失败摘要写入 `ARCHIVE-GATE-REPORT.md`，方便恢复执行。

### 12.3 成功行为

- 生成 `ARCHIVE-GATE-REPORT.md`，列出每一项检查、证据路径和哈希。
- 将 lifecycle phase 从 `VERIFY` 推进到 `ARCHIVE_READY`。
- OpenSpec archive 成功后，再由 lifecycle driver 将状态推进到 `ARCHIVED/COMPLETE`。

## 13. OpenSpec tasks 模板修改

生成的 `tasks.md` 必须显式包含以下阶段，不能把性能和归档隐藏在说明文字中：

```markdown
- [ ] Run real EasyWoS matcher and save matcher evidence
- [ ] Prepare and execute one dispatch record per porting item
- [ ] Integrate leaf-skill output into the real project build
- [ ] Build and test the complete x64 baseline
- [ ] Build and test the complete ARM64 target
- [ ] Run independent red→green negative control
- [ ] Run performance phase, or record explicit user --no-profile
- [ ] Complete independent verification
- [ ] Run strict archive gate
- [ ] Archive OpenSpec change only after archive gate passes
```

任务生成器还应写入相应证据路径，使 task checkbox、生命周期状态和文件证据三者可以互相校验。

## 14. `evidence-validator.js`

该模块作为其他脚本共享的验证库，避免各处重复实现并产生规则漂移。建议提供：

```text
validateSchema(file, schema)
validateSha256(file, expected)
validateCommandEvidence(record)
validateMatcherEvidence(record, combinedSpecs)
validateDispatchChain(request, result, matcherEvidence)
validateNegativeControl(record)
validateIndependentVerifier(record)
validatePerformanceTerminal(record)
validateSourceFingerprint(records)
```

所有验证失败均返回结构化错误：

```json
{
  "ok": false,
  "code": "E_DISPATCH_SPEC_NOT_MATCHED",
  "message": "dispatch spec 146 has no matcher evidence",
  "path": "dispatch/utf8-validate.request.yaml"
}
```

## 15. 测试策略

### 15.1 单元测试

- lifecycle：合法迁移、非法跳转、中断恢复、证据过期、invalidate-from。
- dispatcher：缺 item、错误 spec ID、matched YAML 哈希变化、retry feedback 链。
- matcher：多 scope、组合规则、x86/ARM64 asm 区分、原文件行号证据。
- archive gate：逐项缺失、哈希不符、0 tests、同一 verifier、未跑 profiler、显式 skip。

### 15.2 Fixture 测试

至少准备四套 change fixture：

1. 完整绿色：archive gate 返回 0。
2. 缺失性能证据：返回 `E_PERF_NOT_TERMINAL`。
3. matcher 手填 spec ID：返回 `E_DISPATCH_SPEC_NOT_MATCHED`。
4. producer/verifier 相同：返回 `E_VERIFIER_NOT_INDEPENDENT`。

### 15.3 端到端测试

分两层执行：

- 小型 synthetic fixture：快速覆盖所有状态和故障注入。
- 真实中型项目：覆盖扫描、matcher、dispatcher、全项目 x64/ARM64 构建测试、负向控制、性能产物和 OpenSpec archive。

`lemire/fastvalidate-utf-8` 可作为回归项目之一，重点验证此前出现的 `_mm_movemask_epi8` 漏配、性能证据缺失和提前归档问题。

## 16. 实施顺序

### 阶段 1：先封住提前归档

1. 定义 schemas。
2. 实现 `LIFECYCLE-STATE.yaml` 读写和合法迁移。
3. 实现 `evidence-validator.js`。
4. 实现 `archive-gate.js` 和缺失证据 fixture。
5. 修改 OpenSpec tasks 模板，强制 archive gate 为最后门禁。

完成标准：即使其他适配尚未完成，缺 matcher/dispatch/perf/verifier 证据的 change 也无法被标为可归档。

### 阶段 2：Codex dispatcher 与恢复能力

1. 实现 dispatcher `prepare` 和 `record-result`。
2. 实现 request/result schema、哈希和 feedback 链。
3. 接入 lifecycle `DISPATCH` 阶段。
4. 添加中断恢复和重复执行幂等测试。

完成标准：每个 porting item 都能证明由哪个 matcher 结果、哪些 spec、哪个 producer session 生成。

### 阶段 3：Matcher 正确性

1. 先增加 `_mm_movemask_epi8` 漏配和 `"=r"` 误配的失败测试。
2. 实现一行多 scope。
3. 实现组合规则和逐条证据。
4. 更新需要上下文约束的 spec YAML。
5. 运行 `combine-specs.js` 并重跑全量 matcher tests。

完成标准：两个已知问题红→绿，且现有匹配结果没有未解释的大范围漂移。

### 阶段 4：性能闭环

1. 统一性能终态。
2. 规范 ETL、SpeedScope、paired benchmark 和 checksum 产物。
3. 将管理员权限不足作为 `PAUSED_NEEDS_ADMIN`，明确阻塞归档。
4. 接入 archive gate。

完成标准：未 profile、profile 失败和用户显式 skip 能被可靠区分。

### 阶段 5：全量验证和发布

1. 运行各 skill quick validation。
2. 运行 matcher、dispatcher、lifecycle 和 archive-gate 测试。
3. 运行插件 validator。
4. 对 synthetic fixture 和真实项目完成端到端回归。
5. 更新插件 cachebuster。
6. 按本地 marketplace 流程重新安装插件。
7. 在新 Codex 线程中验证新技能和脚本已被加载。

## 17. 验收标准

只有同时满足以下条件才算改造完成：

- Codex 不依赖 Claude Workflow 注入环境即可推进和恢复生命周期。
- 生命周期任何阶段都能从文件判断“已完成、未完成、失败或证据过期”。
- `_mm_movemask_epi8` 已有防漏配回归测试。
- x86 `"=r"` 已有防误配回归测试。
- 每个 porting item 都有 matcher→dispatch→patch 的可追溯链。
- x64/ARM64 全项目构建测试和 tests discovered 数量可校验。
- 负向控制包含真实红→恢复→绿证据。
- producer 与 verifier 分离可由 session 和 patch hash 证明。
- 性能阶段不会把“未运行”误写为 `STALLED` 或 `CONVERGED`。
- 缺少任一必需证据时 archive gate 返回非零。
- `openspec validate --strict` 和插件 validator 均通过。
- 完整端到端 fixture 最终只能通过 archive gate 进入 `ARCHIVED`。

## 18. 风险与兼容策略

### 18.1 对现有 spec 的匹配漂移

多 scope 可能扩大候选集。实施时应记录修改前后每个 fixture 的候选集差异；新增命中必须有解释，异常扩大则通过组合条件收紧。

### 18.2 证据文件过多

使用小型 JSON/YAML 元数据加二进制文件哈希，不复制完整构建目录。大文件只记录路径、大小和 SHA-256。

### 18.3 Codex 无法从脚本直接调用 skill

adapter 采用 prepare/record 两阶段，不假设 Node 可以调用宿主技能。生命周期 driver 输出下一动作，Codex 执行 leaf skill，再提交结果。这一边界必须在实现和文档中保持明确。

### 18.4 旧 change 目录兼容

旧 change 没有完整证据时，不应自动伪造。可提供一次性 `import-legacy --best-effort`，只导入可证明的信息，其余状态标为 `UNVERIFIED`，需要重新执行对应阶段后才能归档。

### 18.5 性能环境不可用

管理员权限不足、无可终止 workload 或符号解析严重不足都应暂停或失败，不得悄悄降级为成功。只有用户显式 `--no-profile` 才能进入 `SKIPPED_BY_USER`。

## 19. 文件修改边界

后续实施时只修改 EasyWoS 插件源码目录：

```text
C:\Users\chengya\.codex\plugins\qgenie\plugins\easywos
```

不要直接修改：

```text
C:\Users\chengya\.codex\plugins\cache\qgenie\easywos\<version>
C:\Users\chengya\.agents\skills
```

源码实现和测试全部通过后，再使用 plugin-creator 规定的 cachebuster 与 reinstall 流程更新安装副本。
