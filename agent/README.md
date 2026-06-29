# easywos-skills

Expert agent skills for porting x86/x64 code to **Windows on Snapdragon** (**ARM64** and **ARM64EC**).

`easywos-skills` is a skilltree for AI coding agents. It combines an orchestration layer for EasyWoS scan output with a library of focused migration skills for common Windows-on-ARM porting work, including SSE/AVX-to-NEON translation, x64 assembly-to-AArch64 conversion, ARM64 build-system enablement, ARM64EC JIT guidance, and verification workflow generation.

## What this repository contains

```text
skills/
├── easywos-spec/                       # EasyWoS scan orchestration and task generation
├── dispatcher-skill/                   # Routes matched porting items to leaf skills
├── arm64-baseline-porting/             # Baseline ARM64 correctness constraints
├── sse-avx-to-neon/                    # SSE/AVX intrinsics to NEON guidance
├── intrinsics-x64-to-arm64/            # Windows C++ SIMD migration guidance
├── asm-x64-to-arm64/                   # x64 inline/MASM assembly to AArch64 guidance
├── arm64-inlineasm-to-intrinsics/      # ARM64 inline assembly to portable intrinsics
├── enable-windows-arm64/               # Build-system ARM64 enablement guidance
├── jit-arm64ec-virtualalloc-fix-skill/ # ARM64EC JIT executable memory guidance
├── arm64-porting-report/               # Porting report generation
└── leaf-skill-creator/                 # Skill/spec scaffolding assistance
```

See [USAGE.md](USAGE.md) for the full workflow, installation instructions, and examples.

## Installation

Install the skills into a compatible agent skills directory with:

```bash
npx skills add https://github.com/qualcomm/easywos-skills.git
```

Re-run the command after repository updates to pick up new or changed skills.

## Prerequisites

Depending on the workflow you use, you may need:

- Node.js for repository scripts under `skills/*/scripts/`
- OpenSpec CLI for OpenSpec-driven orchestration
- CMake 3.14 or newer for generated verification projects
- A Windows ARM64, ARM64EC, or AArch64-capable build environment for validating generated ports
- MSVC ARM64/ARM64EC, Clang, GCC, or another target compiler appropriate for the project being ported

## Quick start

1. Install the skills.
2. Generate or provide an EasyWoS ARM64 porting YAML report.
3. Run the `easywos-spec` orchestration flow to match porting items to specs.
4. Dispatch each matched item with `dispatcher-skill`.
5. Apply the generated ARM64 implementation changes.
6. Build and run the generated verification workflow.

For details, see [USAGE.md](USAGE.md).

## Development and validation

The repository contains documentation and scripts rather than a single compiled product. Basic validation consists of:

```bash
node skills/dispatcher-skill/scripts/combine-specs.js
node skills/easywos-spec/scripts/setup.js
```

Some scripts have their own package dependencies. For example:

```bash
cd skills/easywos-spec/scripts
npm install
npm test
```

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

This project follows the Developer Certificate of Origin (DCO). Sign off commits with:

```bash
git commit -s
```

## Security

Please do not report security vulnerabilities through public GitHub issues. See [SECURITY.md](SECURITY.md) for reporting guidance.

## Issues and feedback

Use GitHub Issues to report bugs, request documentation improvements, or propose new skill coverage. When reporting a skill issue, include:

- the skill name
- the target architecture and toolchain
- a minimal source snippet or scan item if possible
- expected and actual behavior
- verification steps already attempted

## License

`easywos-skills` is licensed under the [BSD-3-clause License](https://spdx.org/licenses/BSD-3-Clause.html). See [LICENSE.txt](LICENSE.txt) for the full license text.