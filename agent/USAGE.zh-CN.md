# easywos-skills — 使用指南（中文版）

用于将 x86/x64 代码移植到 **Windows on Snapdragon（ARM64 / ARM64EC）** 的专家智能体技能集。

**EasyWoS 是一套端到端的移植解决方案，而不是若干零散的转换工具。** 它把一个项目从
*未经分析的 x64 源码*，一路带到*已移植、已验证、已实测的 ARM64 构建*——中间每一个环节
都是方案的组成部分：

```
扫描 → 规划 → 路由 → 移植 → 验证 → 集成 → 构建 → 测试 → 修复 → 剖析 → 优化 → 沉淀
```

你不需要事先知道哪些内核需要移植、该用哪个配方、怎么测试结果、以及结果是否真的更快。
流水线会逐个回答这些问题，并且**在任一环节未通过验证时拒绝推进**：从未被观察到失败过的
测试不算通过；一个正确但比它替换掉的代码更慢的内核，被视为缺陷而不是交付物。

### 本文怎么读

- **§1–§8 是使用者需要知道的**：适用范围、收益、模型现状、安装、上手、单技能用法、
  性能剖析、常见问题。只想把项目移植过去的话，读到 §8 就够了。
- **§9–§14 是内部逻辑**：仓库结构、流水线内部机制、规格索引、如何新增技能、陷阱清单。
  想扩展 EasyWoS、排查路由问题、或贡献规格时再看。

---

## 1. 适用范围：EasyWoS 适合什么场景

一句话判据：如果把这段代码贴给大模型、它一次就能给出令人满意的移植版本，
那就不需要 EasyWoS。 EasyWoS 针对的是复杂移植场景，"贴过去也不敢信"的那一类——移植结果看起来
对、编译也过、甚至单测也绿，但实际上错了，或者正确却比它替换掉的代码更慢。

### 典型适用场景（复杂的）

| 场景 | 为什么需要流水线，而不是直接问模型 |
|------|-----------------------------------|
| **x64 汇编移植**（内联 `__asm` / MASM `.asm` → AArch64） | 需要逐条对齐语义、标志位、调用约定与并行宽度。这里最容易出的不是编译错误，而是"寄存器宽度悄悄收窄"这类正确性检查抓不到的缺陷。 |
| **x64 intrinsics 移植**（SSE/AVX/AVX2 → NEON） | 大量 x86 指令在 NEON 上**没有一对一映射**：`movemask`、`pcmpestrm`、`gather`、`mulhi`、`pshufb` 的零化语义、`palignr`……每一类都需要一份成熟配方，而不是临场发挥。 |
| **细节密度高，靠临场发挥必错**                           | ABI 双变体、标志位极性、寻址模式、MASM 方言、守卫模式（ 规则多且互相牵连，不是查表能替换的） |
| **功能测试抓不到** | 内存序/原子、并行宽度收窄、无 ARM 路径静默走标量（单测全绿，缺陷只在多线程或性能上显形） |
| **主动优化机会**                                         | DotProd/i8mm 分发、NEON 性能模式、剖析闭环（不是"移植对不对"，是"还能不能更快"） |

### 不需要 EasyWoS 的场景

- 纯 C/C++、没有架构依赖的代码：直接换工具链构建即可。
- 少量能一对一替换的简单 intrinsic（`_mm_add_ps` → `vaddq_f32` 这一类）。
- 单个孤立函数、且你自己能审阅结果的改动。
- 只是想知道"某条 x86 指令的 ARM64 等价是什么"——这是一次问答，不是一条流水线。

体量上的经验判据：**简单工程、移植目标只有几个函数、或者函数调用关系简单**时，流水线的开销往往大于收益；
一旦涉及汇编、硬指令、或者你需要向别人证明"这次移植是对的、而且更快"，就该走流水线。

---

## 2. 使用 EasyWoS 的收益

### 收益一：把"不敢信的移植"变成"可交付的移植"

流水线在两个地方设了硬门禁，这是与直接问模型最本质的差别：

- **负控制门禁**——测试必须先被观察到**变红**才算有效。从未见其失败的绿灯按未验证处理，
  因为一个恒绿的测试可能根本没在跑。
- **性能门禁**——正确但更慢的内核被判为**缺陷**，不是交付物。对比基线必须是真实的回退
  构建，不是手写的朴素实现。

实际效果：在历史运行中，这套门禁抓到过多类"正确性测试抓不到"的问题——例如
`_mm_shuffle_epi8` 与 `vqtbl1q` 的零化条件不同（索引 16–127 时行为分叉）、
以及库在 ARM64 上根本没有 SIMD 路径而静默退化成标量。

### 收益二：经验会累积，不会每次从零开始

每条确认过的经验会被回写进叶子专家技能（`references/specs/*.yaml` / `.md`）。下一个项目
的匹配器会直接命中这条规格，所以**同一个坑不会踩第二次**。这是"技能树"与"每次重新提问"
的根本区别：直接问模型，你拿到的是本次会话的水平；走流水线，你拿到的是所有历史运行沉淀
之后的水平。

已沉淀进规格的经验举例（均来自实测，不是推演）：

- 硬指令类：`pcmpestrm` 这类**没有 NEON 等价**的指令，应该**替换算法**，而不是逐指令模拟。
- 原生指令类：`popcount`、64 位 multiply-high 等场景，用 ARM64 原生指令（`vcntq_u8`、
  `UMULH`）优于忠实转写 x86 的 shuffle-LUT / 四次 `vmull` 方案。
- 依赖链类：单累加器的浮点归约是**延迟受限**的，应拆成多个独立累加器 + `vfmaq_f32`。
- 取舍类：`vrsqrte`+牛顿迭代 是否胜过全精度 `vsqrtq`/`vdivq`，**取决于它是否是瓶颈**——
  两个方向都有实测数据，所以规格里写的是判据，不是口号。

### 收益三：可复现、可审计的过程产物

一次运行会留下：扫描 YAML → `-matched.yaml`（含 `port_spec_ids` 与置信度）→ `tasks.md`
→ 每个内核的 gtest 固件 → 剖析报告（火焰图 + HTML）。进度记录在
`openspec/changes/<change-name>/` 下，运行被中断可以续跑。这意味着你能向他人**证明**
移植是对的、也能说明为什么快了——而不是只能说"模型这么写的"。

### 收益四：低置信度会被标出来，而不是被掩盖

匹配置信度低的条目会带上 `[NEEDS REVIEW]` 继续分发，依赖缺失、工具链缺口、构建命令
有歧义、循环不收敛这几类情况则**无条件停止且不可屏蔽**。流水线宁可停下来问你，也不猜——
因为在这些位置猜，产出的正是"看起来合理但其实错了"的移植。

---

## 3. 模型支持现状

EasyWoS 是一套**技能集（skills）+ 编排逻辑**的端到端解决方案，因此EasyWoS使用的模型是可替换的运行时。技能内容是 Markdown +
YAML，不绑定任何特定模型 API。

| 项 | 现状 |
|----|------|
| 当前验证过的模型 | **Anthropic Claude**（通过 Claude Code / Claude Agent SDK）。目前所有端到端运行、规格沉淀与实测数据都是在 Claude 上取得的。 |
| 对模型能力的要求 | 长上下文（要同时装下扫描 YAML、规格配方与源码，推荐1M的上下文）、可靠的工具调用（读写文件、跑构建、跑测试、跑剖析）、以及能坚持"未验证就不声称"的指令遵循能力。**弱工具调用能力的模型会在外层循环（构建→测试→修复）处失败**，而不是在翻译处失败。 |
| 计划中的验证 | 我们正在积极尝试更多模型。下一步计划验证 **Kimi K3** 与 **Kimi Code**。 |
| 换模型需要改什么 | 技能内容不需要改。由于每个Agent harness有各自的偏好和设置，在调用工具、处理EasyWoS定义的流程和规则时可能会产生分歧。所以每适配一个Agent harness，就需要对应调整EasyWoS的一些设计规则，以此实现兼容不同的Agent harness。 |

---

## 4. 安装

技能从 Claude Code 的 skills 目录加载。本仓库现在作为子目录挂在 `qualcomm/EasyWoS`
仓库下的 `agent/`（即 `agent/skills/...`），所以要用带子路径的方式安装。加上
`--all` 可以把全部技能装到检测到的所有 agent，且不再逐个弹出确认：

```bash
npx skills add qualcomm/EasyWoS/agent --all
```

等价地，用完整 URL：

```bash
npx skills add https://github.com/qualcomm/EasyWoS/tree/main/agent --all
```

如果想装全部技能但限定只装到某个 agent（比如只装 Claude Code），用
`-s "*" -a claude-code -y` 代替 `--all`。注意要用双引号，不要用单引号——
`cmd.exe` 不会剥掉单引号，`-s '*'` 会把带着引号的字面字符串传给命令，
匹配不到任何技能。

仓库更新后重新执行，以获取新增/变更的规格。

### 前置条件

| 用途 | 需要 |
|-----|------|
| 运行流水线脚本 | Node.js（`scripts/` 使用 `js-yaml`；在 `skills/easywos-spec/scripts/` 下执行 `npm install`） |
| 配合 OpenSpec 编排 | OpenSpec CLI（`openspec`），并在 `openspec/config.yaml` 中接好激活规则 |
| 构建/验证 ARM64 产物 | 原生 ARM64 主机（Windows on ARM 或 aarch64 Linux）、MSVC ARM64 工具链（VS 2019+）或 GCC/Clang、CMake 3.14+ |
| 性能剖析（`skills/profiling/`） | Python 3.8+；**仅 `etl-generator` 需要管理员权限的 shell**（内核 CPU 采样使用 NT Kernel Logger）；Node.js 用于提供交互式火焰图 |

---

## 5. 快速上手——移植整个项目

使用 EasyWoS 的方式是**与智能体对话**，而不是自己跑脚本（§11 里的脚本是给调试用的）。
一条命令驱动全部环节——扫描、规划、移植、验证、集成、构建、跑项目自带测试、修复、
剖析、归档：

```
/arm64-port-orchestrator C:/src/my-project
```

这就是完整的调用方式。其余都是可选的调优参数，详见该技能自身的 §0。

- **端到端执行** 遵循以下流程，全程不需要人工干预，除非遇到难以判断的情况

  ```
  扫描 → 规划 → 路由 → 移植 → 验证 → 集成 → 构建 → 测试 → 修复 → 剖析 → 优化 → 沉淀
  ```

- **无条件停止**：依赖缺失、工具链缺口、构建/测试命令有歧义、循环不收敛。这些停止
  **不可屏蔽**，因为在这些地方靠猜会产出"看起来合理但其实是错的"移植。运行若被中断，
  可以从已到达的阶段继续——进度记录在 `openspec/changes/<change-name>/` 下。

**需要用户提供什么：** 流水线在方法上是自主的，但对它无法自行观察到的事实不会猜。
请准备好以下内容，否则会被问到：

- **如何为 ARM64 构建和测试**（在无法自动探测时）。如果项目完全没有 ARM64 配置，
  说明一下——`enable-windows-arm64` 可以帮你加上。
- **一个会退出的负载**（如果你要跑性能循环）。永不退出的服务进程无法直接剖析——见 §7。
- **一台 ARM64 主机。** 交叉编译可以，但验证用的 gtest 和性能剖析必须在 ARM64 上真实执行。

也存在更细粒度的入口——从已有的扫描结果中逐个分发内核、用单个叶子技能移植一段代码
（§6），或只做性能剖析（§7）。

---

## 6. 单独使用某个技能（不走完整流水线）

不必运行整条流水线。每个技能都可独立使用——直接描述任务，对应技能就会激活：

- *"把这个 SSE 内核移植成 NEON"* → `sse-avx-to-neon` / `intrinsics-x64-to-arm64`
- *"把这段 MASM .asm 翻译成 AArch64"* → `asm-x64-to-arm64`
- *"把这段 ARM64 内联汇编改写成 intrinsics，并配 gtest"* → `arm64-inlineasm-to-intrinsics`
- *"给这个 CMake/VS 项目加上 ARM64 支持"* → `enable-windows-arm64`
- *"为这个仓库生成 ARM64 移植报告"* → `arm64-porting-report`
- *"这个 ARM64EC JIT 的代码页分配有问题"* → `jit-arm64ec-virtualalloc-fix-skill`
- *"剖析这个程序，告诉我 CPU 花在哪了"* → `skills/profiling/`（见 §7）

当没有任何具体规格匹配时，`arm64-baseline-porting` 提供必须遵守的 ARM64 不变量
（Windows ARM64 ABI、弱内存序、128 位 NEON 宽度、ARM64EC shim、短缓冲/尾部守卫、
MSVC intrinsic 可移植性），使自由模式的产出仍然正确。

---

## 7. 性能剖析流水线

```
etl-generator  →  perf-sampling-parser  →  perf-optimizer
   （采集）          （按进程 CPU +            （根因 + 源码扫描 +
                      speedscope 导出）          HTML 报告）
```

| 技能 | 职责 |
|------|------|
| `etl-generator` | 在 PerfView CPU 采样下运行目标程序 → 合并后的 `.etl`。**需要管理员 shell。** |
| `perf-sampling-parser` | 解析 `.etl`：按 CPU 给进程排名，为选定进程导出 SpeedScope 火焰图。 |
| `perf-optimizer` | 将热点叶子归因到真正的根因模块，扫描源码中 x64-SIMD/ARM64-NEON 的缺口，汇总 HTML 报告。 |

当传入 `.etl` 而非 SpeedScope JSON 时，`perf-optimizer` 会自动调用 `perf-sampling-parser`；
`perf-sampling-parser` 与 `etl-generator` 共用内置的 `PerfView.exe`。本套件内置了
PerfView + TraceEvent 及 speedscope 网页包，许可与署名见
`skills/profiling/THIRD-PARTY-NOTICES.md`。

在相信一份剖析结果之前，有两点必须知道：

- **PerfView 的 `run` 动作会在目标进程退出时停止采集**，因此无法直接剖析长期运行的服务进程。
  但内核 CPU 采样是**全系统**的：改为剖析一个**会退出**的包装程序，服务进程的调用栈同样会被采到。
- **符号在火焰图里缺失，什么也证明不了。** 它把"从未被调用""被内联""被改名""未符号化"
  混为一谈。要声称移植消除了某个热点，必须在**能真正触发该内核**的负载上剖析**移植前**的构建。

---

## 8. 新用户常见问题（FAQ）

**Q：我必须有 ARM64 机器吗？**
交叉编译可以，但**验证用的 gtest 和性能剖析必须在真实 ARM64 上执行**。没有 ARM64 主机
时，你能拿到移植产物，但拿不到"已验证"这个结论。

**Q：性能剖析必须用管理员权限吗？**
只有 `etl-generator` 需要——内核 CPU 采样走 NT Kernel Logger。解析与报告环节不需要。

**Q：一定要装 OpenSpec 吗？**
不是必须。OpenSpec 用于变更编排与进度留档；不用它也能跑，见
`skills/easywos-spec/references/demo-without-openspec.md`。

**Q：我只想移植一个函数，也要跑整条流水线吗？**
不用。每个技能都能单独调用（§6），直接描述任务即可。

**Q：匹配器一个规格都没匹配上，是不是规格缺失？**
先看**警告**。`code_range exceeds bounds` 这类警告意味着被筛查的源码可能不是你以为的
那一段——此时"零匹配"只是范围给错了，不是规格缺口。清掉警告再判断。

**问：匹配器把*所有*规格都匹配上了，结果没法用。**
这是整文件汇编条目被当成一个整块筛查的典型征兆——大文件总会在某处命中几乎每一条规格。
拆解机制正常情况下会避免这一点（§10）。若没有触发，检查该条目是否写了 `segment: false`、
是否传了 `--no-decompose`、或文件是否未达 400 行阈值。

**问：某个内核的 gtest 失败了，整轮会停下来吗？**
不会。该条目会拿到一份反馈文件并被重新分发给同一个叶子技能，最多重试到预算上限；
若仍失败则标记为待人工复核，整批的其余条目继续推进（§10 的 ⑦′ 步）。

**Q：EasyWoS 支持 Linux/aarch64，还是只支持 Windows？**
移植配方本身与 OS 无关，构建验证在 Windows ARM64 与 aarch64 Linux 上都可以。但
**性能剖析流水线是 Windows 专用的**（基于 PerfView / ETW）。

**Q：产物必须能在 MSVC 上构建吗？**
是。只在 clang 上通过不够。注意 MSVC 特有陷阱：NEON 大括号初始化、`poly64_t` /
`poly128_t`、`vmull_p64` 的 lane 形式、没有 `<arm_acle.h>`、不支持 SVE2；另外
`clang-cl` 会定义 `_MSC_VER`，所以仅凭 `#if defined(_MSC_VER)` 判断不出真正的 MSVC。

**Q：为什么规定移植代码必须由叶子技能产出，不能让智能体手写？**
因为"规格驱动 → 剖析 → 修规格"这个闭环依赖于此。手写产物一旦出问题，你无法区分是
**规格缺口**还是**这次临时编码的偶然失误**，经验也就无法沉淀（见 §2 收益二）。

**Q：我的目标是一个常驻服务，没法剖析怎么办？**
内核 CPU 采样是**全系统**的。改为剖析一个**会退出**的包装/压测程序，服务进程的调用栈
同样会被采到。PerfView 的 `run` 动作在目标进程退出时停止采集，所以直接对常驻进程无效。

**Q：火焰图里那个函数不见了，是不是说明移植生效了？**
不能这么判断。符号缺失把"从未被调用""被内联""被改名""未符号化"混为一谈。要声称移植
消除了某个热点，必须在**能真正触发该内核**的负载上，同样剖析**移植前**的构建作为对照。

**Q：为什么我的 A/B 性能对比波动很大？**
移动端 ARM64 设备在持续负载下会明显降频。做 A/B 前先预热、两轮之间留出冷却时间，并对
两侧使用完全相同的负载与计时方式，否则测到的是温度而不是代码。

**Q：改了规格 `.yaml` 却没生效？**
需要重新生成合并索引：`node skills/dispatcher-skill/scripts/combine-specs.js`（§11）。
对叶子 `SKILL.md` 的文字修改**立即生效**，但 `.yaml` 改完不重新生成就是一个"休眠的修复"。

**Q：流水线会不会自己改我的仓库并提交？**
它会在各阶段门处暂停等你确认——扫描报告后、任务清单生成后、性能循环前、归档前。集成
进真实构建这一步是流程的一部分，但推进节奏由你把关。

---

---

# 内部逻辑（扩展 / 排查 / 贡献时阅读）

以下章节描述 EasyWoS 自身是怎么组织和运转的。只使用它移植项目的话，不需要读到这里。

---

## 9. 仓库内容与角色分工

```
easywos-skills/
├── skills/
│   ├── arm64-port-orchestrator/ # 顶层循环：propose→apply→集成→构建→测试→修复→剖析→归档
│   ├── easywos-spec/            # 编排器：扫描 YAML → 匹配后 YAML → tasks.md（含逐内核验证/重试循环）
│   ├── dispatcher-skill/        # 路由器（第一层）：tasks.md 命令 → 叶子技能
│   ├── arm64-baseline-porting/  # 兜底：无匹配/自由模式下必须遵守的 ARM64 不变量
│   │
│   │   # ── 叶子技能（真正的迁移配方）──
│   ├── sse-avx-to-neon/             # SSE/AVX intrinsics → NEON；CRC32 PCLMULQDQ → PMULL
│   ├── intrinsics-x64-to-arm64/     # SSE/AVX C++ → NEON，守卫与限制的规范处理
│   ├── asm-x64-to-arm64/            # x64 汇编（内联 + MASM .asm）→ AArch64
│   ├── arm64-inlineasm-to-intrinsics/  # ARM64 NEON 内联汇编 → C intrinsics + gtest
│   ├── enable-windows-arm64/        # 为项目构建系统添加 ARM64 配置
│   ├── jit-arm64ec-virtualalloc-fix-skill/  # ARM64EC JIT 代码页分配缺陷
│   │
│   │   # ── 性能剖析流水线（衡量移植效果）──
│   └── profiling/
│       ├── etl-generator/           # 在 PerfView CPU 采样下运行目标程序 → .etl
│       ├── perf-sampling-parser/    # .etl → 按进程 CPU 排名 + SpeedScope 火焰图
│       └── perf-optimizer/          # 火焰图 → 根因模块 + 源码缺口扫描 + HTML 报告
│   │
│   │   # ── 编写 / 报告 ──
│   ├── arm64-porting-report/        # 生成 EasyWoS 风格的移植 YAML
│   ├── leaf-skill-creator/          # 脚手架生成新的叶子技能（含 spec.yaml）
│   │
│   └── combined-spec-summary.yaml   # 由脚本【生成】的全部叶子规格索引（已 gitignore）
└── README.md / USAGE.md / USAGE.zh-CN.md
```

本仓库是一棵*技能树（skilltree）*：一层轻量的编排逻辑，把对 x64 代码库的 EasyWoS 扫描
结果转换成可执行、且与规格（spec）匹配的移植计划；再加上一组负责实际 x64→ARM64 翻译的
叶子技能；以及一条性能剖析流水线，用于衡量移植是否真正带来收益，并把每条确认的经验回写
进规格——使下一个项目的起点更高。四类角色：

- **顶层循环**（`arm64-port-orchestrator`）驱动整个项目的端到端流程——OpenSpec propose →
  easywos-spec 任务生成 → OpenSpec apply → 将移植好的内核集成进项目真实构建 →
  为 ARM64 构建**整个项目** → 运行项目**自带**的测试/基准 → 针对集成失败的自动修复循环 →
  **移植后性能循环（§8.5）** → 归档。它位于 `easywos-spec` **之上**：调用下层技能而非重新实现。
  当你想要"把这个项目移植到 ARM64"的免干预运行时使用它。构建→测试→修复算法见
  `references/outer-loop.md`，性能循环见 `references/perf-optimize-loop.md`。
- **编排层**（`easywos-spec`、`dispatcher-skill`、`arm64-baseline-porting`）决定*移植什么*
  以及*用哪个配方*，并负责逐内核的验证→重试循环（`easywos-spec` §8）。它不包含迁移逻辑。
- **叶子技能**承载迁移逻辑。每个技能持有一到多个*规格*——一份匹配用 `.yaml`
  （机器可读：匹配规则、x64/arm64 构造、陷阱、验证标准）和一份 `.md`（人/智能体可读的配方）。
- **性能剖析**（`skills/profiling/`）衡量移植后的二进制：采集 trace、按进程排 CPU、导出火焰图、
  将热点叶子归因到根因模块、扫描源码中"有 x64 SIMD 但无 NEON"的缺口。可独立使用（§7），
  也会被编排器的 §8.5 自动调用。

---

## 10. 流水线（内部发生了什么）

```
EasyWoS 扫描 YAML
   │  ① arm64-porting-report  （若尚无扫描结果，先生成）
   ▼
easywos-spec 编排器
   │  ② 预检     – 确认叶子技能齐备；重新生成 combined-spec-summary.yaml
   │  ②′ 拆解     – 整个 asm 文件 → 逐内核的分组子条目（§1.4）
   │  ③ 脚本筛查 – spec_matcher.js：将每个条目的 x64 源码与所有规格做正则匹配
   │  ④ LLM 精化 – 剔除误报、拆分 variant_group、给出置信度
   │  ▼
   <name>-matched.yaml      – 原扫描 + 每条目的 port_spec_ids 与 match_confidence
   │  ⑤ tasks.md 生成 – 每个移植条目一条 /dispatcher-skill 命令
   ▼
dispatcher-skill（逐条目）
   │  ⑥ 载入 porting_item + 解析规格 → 路由到叶子技能
   ▼
叶子技能  → ARM64 源码产出（C/intrinsics 或 .asm）
   │  ⑦ 单元测试验证（gtest + CMake + 构建/运行 + 负控制）
   │  ⑦′ 验证→重试循环 – 反馈文件 → 重新分发，最多 K 次（easywos-spec §8）
   ▼
已验证的 ARM64 移植
   │  ⑧ 对照【真实回退实现】做性能剖析（编排器 §8.5 / skills/profiling）
   ▼
既验证正确、又验证收益的 ARM64 移植
```

### 分步说明

**① 取得扫描结果。** 若还没有 EasyWoS 移植 YAML，让智能体生成一份（`arm64-porting-report`
技能）：它会把 x64 热点内核清点为 `porting_items`，含 `file_path`、`code_range`、
`semantics`、`constraints`，以及（针对 fast-path 族）`variant_group` / `target_feature`。

**②–⑤ 运行编排器。** 在 OpenSpec 下，当某个 change 生成 `tasks.md` 时 easywos-spec 技能被触发
（通过 `openspec/config.yaml` 的 `rules.tasks` 接线）。它会：

- 执行**依赖预检**（并重新生成规格索引——见 §11）；
- 执行**脚本筛查**——`spec_matcher.js` 对每个条目已解析的源码做作用域分类，
  并与每条规格的 `match_rules` 做正则匹配，输出候选列表；
- 执行 **LLM 语义精化**——剔除作用域/语义误报、合并冗余规格、按 `target_feature` 拆分
  `variant_group` 条目，并给出 `port_spec_ids` 与 `match_confidence`
  （high/medium/low；low → `[NEEDS REVIEW]`）；
- 写出 **`<scan>-matched.yaml`**（逐条目增强后的扫描），再写出 **`tasks.md`**，
  其 "Dispatcher Execution" 段落里每个条目一条命令。

也可以直接运行匹配器：

```bash
node skills/easywos-spec/scripts/spec_matcher.js \
  --input  <scan.yaml> \
  --specs  skills/combined-spec-summary.yaml \
  --output candidates.json \
  [--threshold N] [--no-decompose]
```

`--threshold` / `--no-decompose` 控制下面所说的拆解预处理；`--input`、`--specs`、
`--output` 三者必填。

> 在解读输出之前，先把匹配器的**警告**（例如 `code_range exceeds bounds`）清掉。
> 警告意味着被筛查的源码可能并不是你以为的那段代码；此时"零匹配"看起来像规格缺口，
> 实际上只是范围给错了。

**整文件汇编拆解（筛查之前的预处理）。** 当一个移植条目指向**整个** `.asm`/`.s`/`.S`
文件时，把它当作一个单元来匹配会在两处失效：大文件总会在某处命中几乎每一条规格的
`match_rules`，候选列表因此丧失全部区分力；而"移植本文件第 1–N 行"也不是叶子技能能落地、
gtest 能逐内核覆盖的任务。所以匹配器会先把文件切成逐内核的分组（`easywos-spec` §1.4）：

- **触发条件**：asm 文件且已解析上下文超过 **400 行**（`--threshold`）时自动拆解；条目写了
  `segment: true` 则无条件拆解。`segment: false` 表示保持整体不拆；`--no-decompose`
  则全局关闭。
- **切分方式**：按内核入口点切分——`cglobal`/`cvisible`（NASM x86inc 方言）或
  `<name> PROC`（MASM）——随后同一逻辑内核的 ISA/尺寸变体会按归一化的分组键合并
  （`foo_16x16_sse2` 与 `foo_8x8_avx2` → 归为 `foo` 组），但批量/元数后缀会保留
  （`foo_x4`），而与名字**粘连**的尾部数字保持独立（`foo8`、`foo16` → 视为不同内核）。
- **产出**：每组一个分组子条目，id 形如 `<parent_id>__<group>`，之后按普通条目筛查、
  分发与验证。

**⑥ 分发。** tasks.md 中每一行都是一次 dispatcher 调用：

```bash
# 已匹配条目（一个或多个规格）
/dispatcher-skill <item-id> --specs 86,87,90 --source <scan>-matched.yaml
# 未匹配条目
/dispatcher-skill <item-id> --mode llm-freeform --source <scan>-matched.yaml
```

dispatcher 载入移植条目，通过 `combined-spec-summary.yaml` 把每个规格 id 解析到对应的
叶子技能与文件，载入该配方并完成路由（多规格合并、跨来源主规格选择，或兜底到 baseline）。
它自身不含任何迁移逻辑。

**⑦ 验证。** 叶子技能产出 ARM64 源码后，单元测试流程会生成 gtest 固件（每条目一个）、
一层纯 C ABI 测试接缝、CMake 以及构建/运行脚本。两条流程——intrinsics
（`references/unit-test-workflow-intrinsics.md`）与汇编（`references/unit-test-workflow.md`）
——依据叶子技能的产出语言选择。模板位于 `skills/easywos-spec/references/`。

固件只有在**被观察到失败过**（负控制门禁：故意注入扰动必须让测试变红，见
`easywos-spec` §7.6）之后才算通过。从未见其变红的绿灯一律按未验证处理。

**⑦′ 失败后重试。** 失败的条目不会被丢下。`easywos-spec` §8 负责逐条目的
**验证→重试循环**：写出一份描述失败原因的反馈文件，带 `--feedback` 把该条目重新分发给同一个
叶子技能，最多重试到预算上限。用尽预算的条目标记为待人工复核，且**不会**阻塞整批的其余条目。
这个循环也有一个脚本化驱动：`skills/easywos-spec/references/port-loop.workflow.js`，
输入一份 matched YAML 加一条构建命令，即可对所有条目跑
分发 → 构建 → 负控制 + gtest → 反馈重试（传 `dryRun: true` 只打印命令、不改动任何文件）。

**⑧ 度量。** 正确性不是全部门槛：一个移植可以完全正确、却比它替换掉的代码**更慢**。
编排器 §8.5 会剖析热点叶子、优化、重新验证，并（在真实移植中）把每条确认的经验回写进叶子规格。
对比基线必须是**真实的回退构建**，不是自己手写的朴素实现。

---

## 11. 生成的规格索引

`skills/combined-spec-summary.yaml` 是**脚本生成**的，不可手改（已 gitignore）。它把每个叶子技能的
`references/specs/*.yaml` 聚合为一张表，带全局唯一 id 和 `source` / `source_sub_dimension` /
`source_id` 路由字段。规格变更后重新生成：

```bash
node skills/dispatcher-skill/scripts/combine-specs.js
```

以下情况后必须重跑：新建叶子技能、修改任一叶子 `*.yaml`、运行 `leaf-skill-creator`。
dispatcher 和匹配器都读这个文件，索引过期就意味着路由过期。

> 只有 `references/specs/*.yaml` 会被聚合。对叶子 `SKILL.md` 的文字修改**立即生效**
> （技能文件本身就是技能），永远不会成为"休眠的修复"；但修改 `.yaml` 后不重新生成，就会。

---

## 12. 叶子技能的结构（以及如何新增）

```
skills/<leaf-skill>/
├── SKILL.md                    # 何时使用 + 配方概览
└── references/specs/
    ├── <dimension>.md          # 一组规格的人/智能体可读配方
    └── <dimension>.yaml        # 机器可读：每条规格的 match_rules、
                                #   x64_constructs、arm64_constructs、
                                #   pitfalls、validation_criteria
```

`.md` 与 `.yaml` 保持一一对应。`.yaml` 的 `match_rules` 必须以 **x86 源码**模式为准
（匹配器筛查的是源码，而不是尚未写出的 ARM 产物）——只匹配 NEON 产物的规则永远不会触发。

用 `leaf-skill-creator` 技能（create 模式）生成新技能，或为已有技能补上缺失的 `spec.yaml`
（add-yaml 模式）。完成后重新生成合并索引（§11）。

**规格必须保持通用。** 规格是共享基础设施：要表达*模式*（x86 构造是什么、ARM64 等价物是什么），
而不是恰好暴露该模式的那个项目。项目专用的规格在别处匹配不到任何东西。

**按经验的类型选择归属。** 技术性的 intrinsic/助记符经验归入叶子规格；流程性或验证性的经验
归入编排器中始终加载的纪律章节，而不是埋在某一个叶子里。

---

## 13. 约定与陷阱

- **`combined-spec-summary.yaml` 是生成物**——绝不手改；规格变更后重新生成。
- **匹配规则针对 x86 源码。** 即使某条规格的目的是性能/产出层面的模式，它仍然需要一个
  x86 源码侧的触发条件，否则会匹配到零个条目。
- **内联汇编走规格路由。** ARM64 内联汇编内核通过正常流水线匹配（匹配器作用域 `inline_asm`）；
  对 `__asm__` 上下文的检测只是次级兜底，用于没有任何规格路由到内联汇编技能的情况。
- **`variant_group` 条目共享同一段源码字节。** 筛查脚本无法区分 `+crc` 基线与 `+pmull`
  快速路径（源码相同）；由 LLM 精化按 `target_feature` 拆分。
- **整个 asm 文件会先被拆解，而不是当成一个整块去匹配。** 超过 400 行
  （`--threshold`）的 `.asm`/`.s`/`.S` 条目会先被切成逐内核的分组子条目，因为大文件几乎会命中
  每一条规格，从而彻底摧毁候选列表的区分力。用 `segment: true` 强制拆解，用 `segment: false`
  阻止，用 `--no-decompose` 全局关闭。若拆解后出现意料之外的分组名，先看
  `easywos-spec` §1.4.2 的分组键归一化规则，再判断是否真是规格缺口。
- **低置信度 → `[NEEDS REVIEW]`。** 这些条目仍会被分发，但标记为需人工核验。
- **移植产物必须来自叶子技能**，不能由智能体手写——否则"规格驱动 → 剖析 → 修规格"这个闭环失效，
  也就无法区分究竟是规格缺口还是临时编码产生的偶然结果。
- **ARM64 产物必须能在 MSVC 上构建，而不只是 clang。** 注意 MSVC 特有陷阱
  （NEON 大括号初始化、`poly64_t`/`poly128_t`、`vmull_p64` 的 lane 形式、无 `<arm_acle.h>`）；
  MSVC 不支持 SVE2。另注意 `clang-cl` 会定义 `_MSC_VER` 却使用 clang 的头文件，
  因此仅凭 `#if defined(_MSC_VER)` 无法识别真正的 MSVC。参见 `arm64-baseline-porting`。
- **短缓冲守卫。** 固定步长的 SIMD 内核必须在任何无条件向量加载之前判断 `len < STRIDE`，
  否则短输入会越界读取、或让 `size_t` 下溢 → 段错误。
- **不要收窄并行宽度。** "保留语义，而非汇编外观"这条规则免除的是汇编的*文本形式*，
  不是它每次迭代处理的数据量。把 N 宽的内核移植成一次处理一项，可以完全正确，
  却仍然输给编译器优化后的标量 C——而这类缺陷任何正确性检查都发现不了。

---

## 14. 参考资料

- **端到端示例：** `skills/easywos-spec/demo/`
  （`zlib-porting-example-record.md`、`complete_smallest_demo_without_openspec.md`）
  以及 `references/demo-without-openspec.md`。
- **输出格式与模板：** `skills/easywos-spec/references/`
  （`matched-yaml-example.md`、`script-output-format.md`，以及 CMake / 构建脚本 /
  单元测试流程模板，还有 `port-loop.workflow.js`——脚本化的验证→重试驱动）。
- **编排契约：** `skills/easywos-spec/SKILL.md`（流水线）与
  `skills/dispatcher-skill/SKILL.md`（路由协议）。
- **外层循环与性能循环：** `skills/arm64-port-orchestrator/references/`
  （`outer-loop.md`、`perf-optimize-loop.md`、`build-test-detection.md`、
  `verification-measurement-discipline.md`）。
- **性能剖析：** `skills/profiling/README.md`。
