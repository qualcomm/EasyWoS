# Third-Party Notices — `skills/profiling`

The profiling skills bundle prebuilt third-party tooling so the agent can parse
ETL traces and render flame graphs without a separate install. These components
are the property of their respective owners and are distributed here under their
own licenses, not under this repository's BSD-3-Clause license.

## PerfView and Microsoft.Diagnostics.Tracing (TraceEvent)

- **Location**: `perf-sampling-parser/scripts/` (`PerfView.exe`,
  `Microsoft.Diagnostics.Tracing.TraceEvent.dll`, and supporting assemblies),
  reused by `etl-generator` and `perf-optimizer`.
- **Project**: https://github.com/microsoft/perfview
- **License**: MIT License, © Microsoft Corporation.

Some native support libraries shipped alongside PerfView (for example
`msdia140.dll`, `KernelTraceControl.dll`, `Dia2Lib.dll`, and the WebView2
runtime) are Microsoft components redistributed as part of the PerfView release.
They remain subject to their original Microsoft license terms. If redistribution
of any such component is not permitted in your context, remove it and configure
the skills to locate a locally installed PerfView instead (the scripts resolve
`PerfView.exe` relative to `perf-sampling-parser/scripts/`; point that at your
own copy).

## speedscope

- **Location**: `perf-optimizer/assets/speedscope/` (web bundle: JS/CSS/WASM,
  fonts, `server.js`).
- **Version**: speedscope@1.25.0
- **Project**: https://github.com/jlfwong/speedscope
- **License**: MIT License, © Jamie Wong.

## Source Code Pro (font)

- **Location**: `perf-optimizer/assets/speedscope/SourceCodePro-*.woff2`
- **License**: SIL Open Font License 1.1 — see
  `perf-optimizer/assets/speedscope/source-code-pro.LICENSE.md`.

---

The profiling **skill instructions and Python scripts** in these directories
(`SKILL.md`, `scripts/*.py`, `references/*.md`) are original to this repository
and are licensed under BSD-3-Clause like the rest of `easywos-skills`.
