// combine-specs.js - Spec Collection Aggregator
//
// Scans all leaf skill yaml files and produces a unified
// skills/combined-spec-summary.yaml with globally unique IDs.
//
// Usage: node skills/dispatcher-skill/scripts/combine-specs.js

const fs = require("fs");
const path = require("path");

const SKILLS_DIR = path.resolve(__dirname, "../../");
const OUTPUT_PATH = path.resolve(SKILLS_DIR, "combined-spec-summary.yaml");

// ---------------------------------------------------------------------------
// Minimal YAML parser for our known spec.yaml structure
// ---------------------------------------------------------------------------

function parseSpecYaml(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  const specs = [];
  let current = null;
  let inMetadata = false;
  let inMatchRules = false;
  let currentRule = null;
  let inDescription = false;
  let descriptionIndent = 0;

  const lines = content.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trimStart();
    const indent = line.length - trimmed.length;

    if (trimmed.startsWith("- id:")) {
      if (currentRule && current) current.metadata.match_rules.push(currentRule);
      currentRule = null;
      if (current) specs.push(current);
      current = {
        id: trimmed.replace("- id:", "").trim(),
        name: "",
        description: "",
        metadata: { match_rules: [] },
      };
      inMetadata = false;
      inMatchRules = false;
      inDescription = false;
      continue;
    }

    if (!current) continue;

    if (trimmed.startsWith("name:") && indent <= 6) {
      current.name = trimmed.replace("name:", "").trim();
      inDescription = false;
      continue;
    }

    if (trimmed.startsWith("description:") && indent <= 6 && !inMatchRules) {
      const val = trimmed.replace("description:", "").trim();
      if (val === ">" || val === "|") {
        inDescription = true;
        descriptionIndent = indent + 2;
        current.description = "";
      } else {
        current.description = val.replace(/^["']|["']$/g, "");
        inDescription = false;
      }
      continue;
    }

    if (inDescription && indent >= descriptionIndent &&
        !trimmed.startsWith("metadata:") && !trimmed.startsWith("x64_constructs:") &&
        !trimmed.startsWith("arm64_constructs:") && !trimmed.startsWith("pitfalls:") &&
        !trimmed.startsWith("validation_criteria:")) {
      current.description += (current.description ? " " : "") + trimmed;
      continue;
    } else if (inDescription) {
      inDescription = false;
    }

    if (trimmed.startsWith("metadata:")) {
      inMetadata = true;
      inDescription = false;
      continue;
    }

    if (inMetadata && trimmed.startsWith("match_rules:")) {
      inMatchRules = true;
      continue;
    }

    if (inMatchRules) {
      if (trimmed.startsWith("- pattern:")) {
        if (currentRule) current.metadata.match_rules.push(currentRule);
        currentRule = {
          pattern: trimmed.replace("- pattern:", "").trim().replace(/^["']|["']$/g, ""),
          type: "",
          scope: "",
          description: "",
        };
        continue;
      }
      if (currentRule && trimmed.startsWith("type:")) {
        currentRule.type = trimmed.replace("type:", "").trim();
        continue;
      }
      if (currentRule && trimmed.startsWith("scope:")) {
        currentRule.scope = trimmed.replace("scope:", "").trim();
        continue;
      }
      if (currentRule && trimmed.startsWith("description:")) {
        currentRule.description = trimmed.replace("description:", "").trim().replace(/^["']|["']$/g, "");
        continue;
      }
      if (indent <= 4 && !trimmed.startsWith("-") && trimmed !== "") {
        if (currentRule) {
          current.metadata.match_rules.push(currentRule);
          currentRule = null;
        }
        inMatchRules = false;
        inMetadata = false;
      }
    }
  }

  if (currentRule && current) current.metadata.match_rules.push(currentRule);
  if (current) specs.push(current);

  return specs;
}

// ---------------------------------------------------------------------------
// YAML output formatting
// ---------------------------------------------------------------------------

function formatInlineValue(v) {
  if (v === null || v === undefined) return "null";
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (typeof v === "string") {
    if (v.match(/[:#{}[\],&*?|>'"!%@`\\]/)) {
      return `"${v.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
    }
    return v;
  }
  return String(v);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const skillDirs = fs.readdirSync(SKILLS_DIR).filter((name) => {
    const fullPath = path.join(SKILLS_DIR, name);
    return fs.statSync(fullPath).isDirectory() && name !== "node_modules";
  });

  const combined = [];
  let globalId = 1;
  const warnings = [];

  for (const skillName of skillDirs.sort()) {
    const specsDir = path.join(SKILLS_DIR, skillName, "references", "specs");
    if (!fs.existsSync(specsDir)) continue;

    const yamlFiles = fs.readdirSync(specsDir).filter((f) => f.endsWith(".yaml"));
    if (yamlFiles.length === 0) {
      warnings.push(`Warning: ${skillName}/references/specs/ has no .yaml files — skipping`);
      continue;
    }

    for (const yamlFile of yamlFiles.sort()) {
      const yamlPath = path.join(specsDir, yamlFile);
      const subDimension = path.basename(yamlFile, ".yaml");

      let specs;
      try {
        specs = parseSpecYaml(yamlPath);
      } catch (e) {
        warnings.push(`Warning: Failed to parse ${skillName}/references/specs/${yamlFile}: ${e.message}`);
        continue;
      }

      for (const spec of specs) {
        combined.push({
          id: globalId,
          name: spec.name,
          source: skillName,
          source_sub_dimension: subDimension,
          source_id: spec.id,
          description: spec.description,
          metadata: spec.metadata,
        });
        globalId++;
      }
    }
  }

  // Build output YAML
  let output = "";
  output += `version: "1.0"\n`;
  output += `generated_at: "${new Date().toISOString().slice(0, 10)}"\n`;
  output += `description: Combined spec collection aggregated from all leaf skills\n`;
  output += `total_specs: ${combined.length}\n`;
  output += `\n`;
  output += `specs:\n`;

  for (const spec of combined) {
    output += `  - id: ${spec.id}\n`;
    output += `    name: ${formatInlineValue(spec.name)}\n`;
    output += `    source: ${spec.source}\n`;
    output += `    source_sub_dimension: ${spec.source_sub_dimension}\n`;
    output += `    source_id: ${formatInlineValue(spec.source_id)}\n`;
    output += `    description: >\n`;
    output += `      ${spec.description}\n`;
    output += `    metadata:\n`;
    output += `      match_rules:\n`;
    for (const rule of spec.metadata.match_rules) {
      output += `        - pattern: ${formatInlineValue(rule.pattern)}\n`;
      output += `          type: ${rule.type}\n`;
      output += `          scope: ${rule.scope}\n`;
      output += `          description: ${formatInlineValue(rule.description)}\n`;
    }
  }

  fs.writeFileSync(OUTPUT_PATH, output, "utf8");

  // Report
  if (warnings.length > 0) {
    console.log("Warnings:");
    warnings.forEach((w) => console.log(`  ${w}`));
    console.log();
  }
  console.log(`Combined ${combined.length} specs from ${new Set(combined.map((s) => s.source)).size} leaf skill(s)`);
  console.log(`Output: ${OUTPUT_PATH}`);
}

main();
