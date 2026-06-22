# Matched YAML Example Output

Given `example/x64-to-arm64-asm-porting.yaml` as input:

```yaml
schema: x64-to-arm64-porting
description: |
  Describes two x86_64 assembly code snippets that need to be ported to ARM64.

porting_items:

  - id: function-prolog
    title: Function Prolog (Stack Frame Setup)
    file_path: src/compute_sum.asm
    code_range: 21-30
    # ... (original fields preserved) ...
    port_spec_ids: [12]
    match_confidence:
      rules_hit: 3
      scope_verified: true
      llm_confidence: high

  - id: addition-logic
    title: SIMD Addition with Scalar Accumulation
    file_path: src/compute_sum.asm
    code_range: 47-61
    # ... (original fields preserved) ...
    port_spec_ids: [13, 15]
    match_confidence:
      rules_hit: 5
      scope_verified: true
      llm_confidence: high
```

The output file is named `<original-filename>-matched.yaml` (e.g., `x64-to-arm64-asm-porting-matched.yaml`).
