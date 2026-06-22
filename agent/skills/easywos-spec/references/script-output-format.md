# Script Output Format (JSON)

The screening script (`spec_matcher.js`) outputs a JSON file with the following structure:

```json
{
  "candidates": [
    {
      "porting_item_id": "function-prolog",
      "matches": [
        { "spec_id": 12, "spec_name": "Callee-Saved Register Save/Restore", "rules_hit": 3, "matched_rules": ["pattern1", "pattern2", "pattern3"] },
        { "spec_id": 13, "spec_name": "Flag Discipline", "rules_hit": 1, "matched_rules": ["pattern1"] }
      ]
    },
    {
      "porting_item_id": "addition-logic",
      "matches": []
    }
  ]
}
```

Each entry in `candidates` corresponds to one porting_item from the input YAML. The `matches` array contains all specs whose `match_rules` produced at least one hit during scope-filtered regex matching. An empty `matches` array means no spec patterns matched that porting_item.
