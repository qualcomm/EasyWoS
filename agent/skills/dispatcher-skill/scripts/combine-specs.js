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
const yaml = require(path.resolve(SKILLS_DIR, "easywos-spec/scripts/node_modules/js-yaml"));

// ---------------------------------------------------------------------------
// YAML loading
// ---------------------------------------------------------------------------

function parseSpecYaml(filePath) {
  const data = yaml.load(fs.readFileSync(filePath, "utf8"));
  if (!data || !Array.isArray(data.specs)) {
    throw new Error("expected top-level specs array");
  }
  return data.specs;
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

  const output = yaml.dump({
    version: "1.0",
    generated_at: new Date().toISOString().slice(0, 10),
    description: "Combined spec collection aggregated from all leaf skills",
    total_specs: combined.length,
    specs: combined,
  }, {
    noRefs: true,
    lineWidth: 160,
    sortKeys: false,
  });

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
