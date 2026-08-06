# Memory Addressing Modes (x64 → arm64)

x64 has a single rich form `[base + index*scale + disp32]`. arm64 splits these
into separate forms; not all combinations have a single-instruction equivalent.
Pre/post-indexed and load-pair forms unique to arm64 should be exploited where
the x64 source did multi-step pointer arithmetic.

## Plain Load / Store

**x64**: `[reg]` for plain load.

**ARM64**: `[xN]` — register-indirect, no offset. Width is encoded in the
mnemonic and register name (`ldr w0, [x1]` for 32-bit, `ldr x0, [x1]` for 64-bit).

**Workaround**:
| x64 | arm64 |
|---|---|
| `mov rax, [rsi]` | `ldr x0, [x1]` |
| `mov eax, [rsi]` | `ldr w0, [x1]` |
| `mov [rsi], rax` | `str x0, [x1]` |

**Validation**:
- All `mov reg, [reg]` patterns become `ldr` (load) or `str` (store).
- Register width matches via `w` (32-bit) or `x` (64-bit).

## Immediate Offset (`[base + disp]`)

**x64**: `[rsi + 16]` — 32-bit signed displacement.

**ARM64**: `[xN, #imm]` — 12-bit unsigned immediate, scaled by access size
(so 4096 × access size is the practical maximum). Negative offsets and
larger ranges require `add` + `ldr`.

**Workaround**:
| x64 | arm64 |
|---|---|
| `mov rax, [rsi + 16]` | `ldr x0, [x1, #16]` |
| `mov rax, [rsi + 4096]` | `ldr x0, [x1, #4096]` (8-byte access × 512 = 4096; legal) |
| `mov rax, [rsi - 16]` | `ldur x0, [x1, #-16]` (unscaled) |
| `mov rax, [rsi + 65536]` | `add xT, x1, #65536; ldr x0, [xT]` |

**Pitfalls**:
- `ldr` immediate is **scaled** by access size: `ldr w0, [x1, #4]` reads `[x1+4]`, but the immediate field stores `1`. The scaled max is `4 × 4095` = 16380 for word access, `8 × 4095` = 32760 for double-word.
- Negative or unscaled offsets need `ldur`/`stur` (unscaled, signed 9-bit imm), or pre-compute the address.

**Validation**:
- All `[base + disp]` translations stay within the 12-bit scaled-immediate range, or use `ldur`/`stur` for negative/unscaled offsets, or compute the address into a register.

## Register Index (`[base + index]`)

**x64**: `[rsi + rdx]`.

**ARM64**: `[xN, xM]` — register offset (no shift).

**Workaround**:
```
mov rax, [rsi + rdx]   →   ldr x0, [x1, x2]
```

**Pitfalls**:
- arm64 register-offset addressing has no displacement — `[xN, xM, #imm]` is **not** a valid form. See "scaled+disp" below.

**Validation**:
- `[base + index]` → `[xN, xM]` only when there is no displacement.

## Scaled Index (`[base + index*scale]`)

**x64**: `[rsi + rdx*4]` — scale factor 1, 2, 4, or 8.

**ARM64**: `[xN, xM, lsl #N]` — shift the index by N before adding. The shift
amount must equal the log2 of the access size (e.g. `lsl #2` for word access,
`lsl #3` for double-word). Scales not matching access size require explicit
`add`.

**Workaround**:
| x64 | arm64 |
|---|---|
| `mov rax, [rsi + rdx*8]` | `ldr x0, [x1, x2, lsl #3]` |
| `mov eax, [rsi + rdx*4]` | `ldr w0, [x1, x2, lsl #2]` |
| `mov eax, [rsi + rdx*8]` | `add xT, x1, x2, lsl #3; ldr w0, [xT]` (scale ≠ access) |

**Pitfalls**:
- Shift amount must match access-size log2; mismatched scale requires the multi-instruction form.
- Sign-extending the index is a separate `sxtw`: `[xN, wM, sxtw #2]` extends `wM` to 64-bit before the shift+add.

**Validation**:
- `[base, index, lsl #N]` form has `N == log2(access_size)`.
- Mismatched scales are decomposed into `add` + simple load.

## Combined Scale + Displacement

**x64**: `[rsi + rdx*4 + 16]` — fully general single-instruction form.

**ARM64**: **No combined scaled+disp form.** Two instructions required:
```gas
add xT, x1, x2, lsl #2
ldr w0, [xT, #16]
```

**Workaround**: Compute `base + index*scale` into a temp, then load with disp.
If the same temp is used for several loads, hoist the `add` once.

**Pitfalls**:
- This is the most common spot where x64 `lea` and `mov` collapse pointer
  arithmetic in 1 instruction; arm64 always needs 2. Expect the arm64 port to
  be 1.5×–2× the instruction count for memory-heavy code.

**Validation**:
- No attempt to write `[xN, xM, lsl #N, #imm]` (not a valid form).
- Combined scale+disp is decomposed into `add` + `ldr`/`str`.

## RIP-Relative Addressing

**x64**: `[rip + symbol]` — single instruction, 32-bit signed offset to a
symbol relative to the next instruction's address. `lea rax, [rip + symbol]`
materializes the address.

**ARM64**: Two instructions: `adrp xN, symbol` (4 KB-page address, 21-bit
offset = ±4 GB range) + `add xN, xN, :lo12:symbol` (12-bit page offset). For
GOT-indirect: `adrp xN, :got:symbol` + `ldr xN, [xN, :got_lo12:symbol]`.

**Workaround**:
| x64 | arm64 |
|---|---|
| `lea rax, [rip + symbol]` | `adrp x0, symbol; add x0, x0, :lo12:symbol` |
| `mov rax, [rip + symbol]` | `adrp x0, symbol; ldr x0, [x0, :lo12:symbol]` |
| `mov rax, [rip + sym@GOTPCREL]` | `adrp x0, :got:sym; ldr x0, [x0, :got_lo12:sym]` |

**Pitfalls**:
- `adrp` rounds the address to a 4 KB page boundary; the `:lo12:` add reconstructs the precise byte offset. Forgetting the `add` (or `ldr` with `:lo12:`) leaves the address page-aligned only.
- Far symbols (>±4 GB) require GOT indirection; pure `adrp+add` will fail at link time.

**Validation**:
- All `[rip + symbol]` patterns become `adrp` + (`add` for address, `ldr` for value).
- GOT-indirect symbols use `:got:` / `:got_lo12:` relocations.

## Pre-Indexed and Post-Indexed Addressing (arm64-only)

**x64**: No combined load-and-update-pointer form (would need two instructions).

**ARM64**: Pre-index `[xN, #imm]!` reads and then `xN += imm`. Post-index
`[xN], #imm` reads, then `xN += imm`. These collapse a load + pointer-bump
into one instruction — exploit when the x64 source did `mov ... + add rsi, 8`.

**Workaround**:
```asm
; x64
mov rax, [rsi]
add rsi, 8

; arm64 — collapse to one instruction
ldr x0, [x1], #8   ; post-indexed
```

**Pitfalls**:
- `[xN, #imm]!` (pre-index) and `[xN], #imm` (post-index) update `xN` even if
  the load is conditional/exception-prone — the side effect on `xN` is real.
  Surrounding code must not assume `xN` was unchanged.

**Validation**:
- Sequences of "load then increment pointer" use post-indexed form.
- Sequences of "increment pointer then load" use pre-indexed form.

## Load-Pair / Store-Pair (`ldp` / `stp`)

**x64**: No equivalent — would need two `mov` instructions.

**ARM64**: `ldp x0, x1, [x2, #16]` reads two consecutive 8-byte values into
two registers in one instruction. `stp` is the dual. Standard prologue/epilogue
spill uses `stp x29, x30, [sp, #-16]!` (pre-indexed) and `ldp x29, x30, [sp],
#16` (post-indexed).

**Workaround**: Two consecutive same-width loads (or stores) collapse into
one `ldp`/`stp`.

**Pitfalls**:
- `ldp`/`stp` immediate is **signed 7-bit, scaled** by the access size — much
  smaller range than single `ldr`. For 8-byte access, range is ±504 bytes.
- The two registers must be the same width (`x0,x1` or `w0,w1` — not mixed).

**Validation**:
- Adjacent same-width loads/stores are merged into `ldp`/`stp`.
- `stp`/`ldp` offsets stay within the signed 7-bit scaled range.

## Stack Frame Operations (PUSH/POP → STP/LDP)

**x64**: `push reg` / `pop reg` — implicit RSP adjustment.

**ARM64**: No PUSH/POP mnemonics. Use STP/LDP with pre/post-index addressing.

**Workaround**:
| x64 | arm64 |
|---|---|
| `push rbx` | `str x19, [sp, #-16]!` (pad to 16) |
| `pop rbx` | `ldr x19, [sp], #16` |
| `push rbx; push rsi` | `stp x19, x20, [sp, #-16]!` |
| `pop rsi; pop rbx` | `ldp x19, x20, [sp], #16` |

**Pitfalls**:
- 8-byte SP adjustment is illegal on arm64 — single saves must pad to 16
  bytes. See [[register-and-abi]] stack alignment rule.
- Pre-index (`[sp, #-N]!`) on STP is the standard prologue spill — separate
  `sub sp, sp, #N` followed by `stp` is **not** equivalent under async
  signal: a signal between the two instructions sees inconsistent state. The
  pre-index form is atomic w.r.t. the SP update.

**Validation**:
- No `push`/`pop` mnemonics remain in arm64 output.
- Prologue saves use pre-indexed `stp [sp, #-N]!`; epilogue restores use post-indexed `ldp [sp], #N`.
- All such adjustments are multiples of 16.

## Stride Units: Elements vs Bytes (silent wrong-output trap)

**Not a mnemonic mapping — a contract trap.** A strided 2-D kernel advances each
pointer by a `stride`. Whether that stride arrives **in elements or in bytes**
depends on the pointer's element type, and the asm must scale accordingly. For a
1-byte element (`char`/`uint8`) element-stride == byte-stride and the naive port
"just works"; for a wider element (`int16`, `int32`, …) the kernel **must scale
the stride to bytes** (`lsl xN, xN, #log2(sizeof element)`) before using it as a
pointer increment.

This bites kernels with pointers of **different element widths on each side** —
a widening/narrowing copy or filter where input and output (or src and dst) are
not the same type. The wider-typed pointer's stride needs scaling; the 1-byte
side does not. It is silent because the same-width variants (both sides 1 byte,
or both the same wide type used consistently) happen to have matching
element/byte handling, so the bug only surfaces on the differently-typed side.

```gas
// A kernel whose dst is a 2-byte element, dstStride passed in ELEMENTS:
// WRONG — advances dst by element count, overlapping every other row
//   (the x64 source may hide this: it did `add r1, r1` and a comment claimed bytes)
str     q0, [x2]
add     x2, x2, x3          // x3 = element stride — too small by 2× for int16 dst

// CORRECT — convert the wide-typed side's stride to bytes once, up front
lsl     x3, x3, #1          // elements → bytes (2-byte element)
...
str     q0, [x2]
add     x2, x2, x3
```

Scale exactly the wide-typed pointer(s) — a `src` whose element type is wider
than the other side needs its `srcStride` scaled too; the 1-byte side never does.
(Codebases that name input/output type pairs with a suffix convention — e.g. a
narrow↔wide / 8-bit↔16-bit family — must scale the wide-typed side.)

**Procedure**: for each pointer, read its element type from the destination
declaration and derive whether its stride argument is in elements or bytes. Scale
exactly the wide-typed side(s); do not blindly copy the x64 source's stride
handling (it encodes its own private convention — see the contract rule in
[[register-and-abi]]).

**Pitfalls**:
- The x64 source's `add r1, r1` (or absence of it) is **not** authoritative — a
  port comment claiming "the caller passes a byte stride" is a classic source of
  this bug. Trust the destination prototype's pointer type.
- Same-width strides matching bytes is a coincidence of equal element size, not a
  general guarantee — re-check every variant whose pointers differ in width.

**Validation**:
- Every pointer whose element type is >1 byte has its element-stride scaled to a
  byte-stride (`lsl #log2(sizeof element)`) before use as an increment.
- Stride-unit handling is derived from the destination declaration's pointer
  types, and numeric output is diffed against the reference (failure-tested).

## See Also

- [[register-and-abi]] for SP alignment rule and red-zone discussion.
- [[standalone-asm-dialect]] for `qword ptr` → `ldr x` width annotation.
- [[memory-model-and-atomics]] for ordering semantics around loads/stores.
