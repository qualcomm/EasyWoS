# Contributing to easywos-skills

Thank you for your interest in contributing to `easywos-skills`.

This repository contains AI agent skills, reference specifications, and validation helpers for Windows on Snapdragon and ARM64/ARM64EC porting workflows. Contributions should improve correctness, maintainability, documentation quality, or verification coverage.

## Ways to contribute

You can contribute by:

- fixing documentation issues
- improving existing skill instructions
- adding missing ARM64 or ARM64EC porting guidance
- adding or improving machine-readable spec YAML files
- improving validation scripts and tests
- reporting reproducible issues with a skill workflow

## Before opening a pull request

1. Search existing issues and pull requests to avoid duplicate work.
2. Keep changes focused and easy to review.
3. Avoid including confidential, proprietary, export-controlled, or third-party content unless you have confirmed it is approved for public release.
4. Validate generated or edited YAML and scripts.
5. Update documentation when behavior changes.

## Development setup

Some repository scripts require Node.js dependencies.

```bash
cd skills/easywos-spec/scripts
npm install
npm test
```

From the repository root, useful validation commands include:

```bash
node skills/dispatcher-skill/scripts/combine-specs.js
node skills/easywos-spec/scripts/setup.js
```

## Adding or changing a skill

When adding or changing a leaf skill:

1. Update `skills/<skill-name>/SKILL.md`.
2. Add or update human-readable references under `skills/<skill-name>/references/`.
3. If the skill participates in EasyWoS matching, add or update corresponding `references/specs/*.yaml` files.
4. Ensure YAML match rules target x86/x64 source patterns where applicable.
5. Regenerate `skills/combined-spec-summary.yaml` with:

```bash
node skills/dispatcher-skill/scripts/combine-specs.js
```

6. Run relevant tests and document the expected workflow.

## Pull request expectations

A pull request should include:

- a clear summary of the change
- rationale for the change
- validation steps performed
- any known limitations
- updates to documentation or examples when applicable

## Developer Certificate of Origin

This project uses the Developer Certificate of Origin (DCO). By contributing, you certify that you have the right to submit the contribution under this project's license.

Sign off each commit with:

```bash
git commit -s
```

The sign-off adds a line similar to:

```text
Signed-off-by: Your Name <your.email@example.com>
```

## Code of conduct

Be respectful and constructive in all project interactions. Focus feedback on technical content, reproducibility, and project goals.

## Reporting security issues

Do not report security vulnerabilities through public issues. Follow the process in [SECURITY.md](SECURITY.md).