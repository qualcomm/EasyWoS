/**
 * EasyWoS-Spec + OpenSpec Integration Setup Script
 *
 * Sets up the environment for joint usage of easywos-spec skill with OpenSpec:
 * 1. Verifies required dependencies (js-yaml)
 * 2. Validates the spec collection file exists and is well-formed
 * 3. Ensures openspec/config.yaml has the activation rule for easywos-spec
 * 4. Verifies the SKILL.md is in place
 * 5. Runs a quick sanity check of the spec_matcher against a minimal input
 *
 * Usage:
 *   node skills/easywos-spec/scripts/setup.js [--spec-collection <path>]
 *
 * Options:
 *   --spec-collection  Path to combined-spec-summary.yaml (default: auto-detect)
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PROJECT_ROOT = path.resolve(__dirname, "../../..");
const SCRIPTS_DIR = path.resolve(__dirname);
const SKILL_DIR = path.resolve(__dirname, "..");

const DEFAULTS = {
  specCollection: path.join(PROJECT_ROOT, "openspec/changes/x64-intrinsics-to-arm64-spec-list/combined-spec-summary.yaml"),
  openspecConfig: path.join(PROJECT_ROOT, "openspec/config.yaml"),
  skillMd: path.join(SKILL_DIR, "SKILL.md"),
  specMatcher: path.join(SCRIPTS_DIR, "spec_matcher.js"),
};

const ACTIVATION_RULE = "When the change involves x64-to-arm64 porting (porting_items present)";

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

function parseArgs() {
  const args = process.argv.slice(2);
  const parsed = { specCollection: DEFAULTS.specCollection };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--spec-collection" && args[i + 1]) {
      parsed.specCollection = path.resolve(args[++i]);
    }
  }
  return parsed;
}

// ---------------------------------------------------------------------------
// Setup steps
// ---------------------------------------------------------------------------

let stepCount = 0;
let passCount = 0;
let failCount = 0;

function step(name, fn) {
  stepCount++;
  process.stdout.write(`[${stepCount}] ${name} ... `);
  try {
    const result = fn();
    if (result === false) {
      console.log("SKIP");
    } else {
      console.log("OK");
      passCount++;
    }
  } catch (e) {
    console.log("FAIL");
    console.log(`    Error: ${e.message}`);
    failCount++;
  }
}

function checkDependencies() {
  const jsYamlPath = path.join(SCRIPTS_DIR, "node_modules/js-yaml/index.js");
  if (!fs.existsSync(jsYamlPath)) {
    console.log("\n    Installing js-yaml...");
    execSync("npm install js-yaml --quiet", { cwd: SCRIPTS_DIR, stdio: "pipe" });
    if (!fs.existsSync(jsYamlPath)) {
      throw new Error("Failed to install js-yaml");
    }
  }
}

function validateSpecCollection(specPath) {
  if (!fs.existsSync(specPath)) {
    throw new Error(`Spec collection not found: ${specPath}`);
  }

  const yaml = require(path.join(SCRIPTS_DIR, "node_modules/js-yaml"));
  const data = yaml.load(fs.readFileSync(specPath, "utf8"));

  if (!data.specs || !Array.isArray(data.specs)) {
    throw new Error("Spec collection missing 'specs' array");
  }

  const specsWithRules = data.specs.filter(
    (s) => s.metadata && s.metadata.match_rules && s.metadata.match_rules.length > 0
  );

  if (specsWithRules.length === 0) {
    throw new Error("No specs with match_rules found");
  }

  console.log(`\n    Found ${data.specs.length} specs, ${specsWithRules.length} with match_rules`);
}

function checkOpenSpecConfig() {
  if (!fs.existsSync(DEFAULTS.openspecConfig)) {
    throw new Error(`openspec/config.yaml not found at: ${DEFAULTS.openspecConfig}`);
  }

  const content = fs.readFileSync(DEFAULTS.openspecConfig, "utf8");
  if (!content.includes(ACTIVATION_RULE)) {
    throw new Error(
      "openspec/config.yaml missing EasyWoS-Spec activation rule in rules.tasks.\n" +
      "    Add the following to config.yaml:\n" +
      "    rules:\n" +
      "      tasks:\n" +
      '        - "When the change involves x64-to-arm64 porting (porting_items present), MUST invoke the EasyWoS-Spec skill..."'
    );
  }
}

function checkSkillMd() {
  if (!fs.existsSync(DEFAULTS.skillMd)) {
    throw new Error(`SKILL.md not found at: ${DEFAULTS.skillMd}`);
  }

  const content = fs.readFileSync(DEFAULTS.skillMd, "utf8");
  if (!content.includes("name: easywos-spec")) {
    throw new Error("SKILL.md missing expected frontmatter (name: easywos-spec)");
  }
  if (!content.includes("dispatcher-skill")) {
    throw new Error("SKILL.md missing dispatcher protocol section");
  }
}

function checkSpecMatcher() {
  if (!fs.existsSync(DEFAULTS.specMatcher)) {
    throw new Error(`spec_matcher.js not found at: ${DEFAULTS.specMatcher}`);
  }
}

function sanityCheck(specPath) {
  const yaml = require(path.join(SCRIPTS_DIR, "node_modules/js-yaml"));

  // Create minimal test input
  const testInput = {
    schema: "x64-to-arm64-porting",
    porting_items: [
      {
        id: "sanity-check",
        context: "    push    %rbx\n    jne     .loop\n",
      },
    ],
  };

  const tmpInput = path.join(SCRIPTS_DIR, "_setup_sanity_input.yaml");
  const tmpOutput = path.join(SCRIPTS_DIR, "_setup_sanity_output.json");

  try {
    fs.writeFileSync(tmpInput, yaml.dump(testInput), "utf8");

    execSync(
      `node "${DEFAULTS.specMatcher}" --input "${tmpInput}" --specs "${specPath}" --output "${tmpOutput}"`,
      { stdio: "pipe", encoding: "utf8" }
    );

    if (!fs.existsSync(tmpOutput)) {
      throw new Error("spec_matcher.js did not produce output");
    }

    const result = JSON.parse(fs.readFileSync(tmpOutput, "utf8"));
    if (!result.candidates || result.candidates.length !== 1) {
      throw new Error("Unexpected output structure from spec_matcher.js");
    }

    const matches = result.candidates[0].matches;
    if (matches.length === 0) {
      throw new Error("Sanity check failed: expected at least 1 spec match for push %rbx + jne");
    }

    console.log(`\n    Sanity check matched ${matches.length} spec(s): ${matches.map((m) => m.spec_name).join(", ")}`);
  } finally {
    try { fs.unlinkSync(tmpInput); } catch (e) {}
    try { fs.unlinkSync(tmpOutput); } catch (e) {}
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const args = parseArgs();

  console.log("╔══════════════════════════════════════════════════════════════╗");
  console.log("║   EasyWoS-Spec + OpenSpec Integration Setup                 ║");
  console.log("╚══════════════════════════════════════════════════════════════╝");
  console.log();
  console.log(`Project root:    ${PROJECT_ROOT}`);
  console.log(`Spec collection: ${args.specCollection}`);
  console.log();

  step("Check dependencies (js-yaml)", checkDependencies);
  step("Validate spec collection", () => validateSpecCollection(args.specCollection));
  step("Check openspec/config.yaml activation rule", checkOpenSpecConfig);
  step("Check SKILL.md exists and well-formed", checkSkillMd);
  step("Check spec_matcher.js exists", checkSpecMatcher);
  step("Run sanity check (minimal matching test)", () => sanityCheck(args.specCollection));

  console.log();
  console.log("══════════════════════════════════════════════════════════════");
  console.log(`Setup complete: ${passCount} passed, ${failCount} failed`);
  console.log();

  if (failCount === 0) {
    console.log("Integration ready! Usage workflow:");
    console.log();
    console.log("  1. EasyWoS scans source code → produces <name>.yaml");
    console.log("  2. Run spec matching:");
    console.log(`     node skills/easywos-spec/scripts/spec_matcher.js \\`);
    console.log(`       --input <name>.yaml \\`);
    console.log(`       --specs ${path.relative(PROJECT_ROOT, args.specCollection)} \\`);
    console.log(`       --output <name>-candidates.json`);
    console.log();
    console.log("  3. Use OpenSpec to create a change:");
    console.log("     /opsx:propose <change-name>");
    console.log();
    console.log("  4. EasyWoS-Spec skill auto-activates during tasks.md generation");
    console.log("     (triggered by config.yaml rules.tasks)");
    console.log();
    console.log("  5. Implement tasks:");
    console.log("     /opsx:apply <change-name>");
    console.log();
  } else {
    console.log("Fix the issues above before using EasyWoS-Spec with OpenSpec.");
    process.exit(1);
  }
}

main();
