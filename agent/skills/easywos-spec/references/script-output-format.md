# Script Output Format (JSON)

The screening script (`spec_matcher.js`) outputs a JSON file with the following structure:

```json
{
  "matcher": {
    "schema_version": 1,
    "executed_at": "2026-10-08T10:00:00.000Z",
    "script": "C:/easywos/skills/easywos-spec/scripts/spec_matcher.js",
    "script_sha256": "...",
    "input": "C:/project/scan.yaml",
    "input_sha256": "...",
    "specs": "C:/easywos/skills/combined-spec-summary.yaml",
    "specs_sha256": "..."
  },
  "candidates": [
    {
      "porting_item_id": "function-prolog",
      "matches": [
        {
          "spec_id": 12,
          "spec_name": "Callee-Saved Register Save/Restore",
          "rules_hit": 1,
          "matched_rules": ["pattern1"],
          "matched_groups": [],
          "evidence": [
            {
              "evidence_id": "match-function-prolog-12-1",
              "spec_id": 12,
              "rule_id": "callee-saved-push",
              "group_id": null,
              "file": "src/kernel.asm",
              "line": 42,
              "context_line": 2,
              "scopes": ["instruction"],
              "pattern": "pattern1",
              "excerpt": "push rbx"
            }
          ]
        },
        {
          "spec_id": 13,
          "spec_name": "Flag Discipline",
          "rules_hit": 1,
          "matched_rules": ["pattern1"],
          "matched_groups": [],
          "evidence": [
            { "evidence_id": "match-function-prolog-13-1", "spec_id": 13, "file": "src/kernel.asm", "line": 46, "scopes": ["instruction"], "pattern": "pattern1", "excerpt": "jne .loop" }
          ]
        }
      ]
    },
    {
      "porting_item_id": "addition-logic",
      "matches": []
    }
  ]
}
```

The top-level `matcher` object proves which script, scan, and combined spec file
produced the result. The lifecycle archive gate re-hashes those files and rejects
stale evidence.

Each entry in `candidates` corresponds to one porting_item from the input YAML.
The `matches` array contains all specs whose legacy `match_rules` or compound
`match_groups` produced a hit. Every match includes concrete evidence with the
original source file and line. An empty `matches` array means no spec patterns
matched that porting_item.
