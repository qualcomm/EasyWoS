const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PLUGIN_ROOT = path.resolve(__dirname, "../..");
const yaml = require(path.join(
  PLUGIN_ROOT,
  "skills/easywos-spec/scripts/node_modules/js-yaml"
));

function parseArgs(argv) {
  const parsed = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      parsed._.push(token);
      continue;
    }
    const key = token.slice(2).replace(/-/g, "_");
    const value = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true;
    if (Object.prototype.hasOwnProperty.call(parsed, key)) {
      parsed[key] = Array.isArray(parsed[key]) ? [...parsed[key], value] : [parsed[key], value];
    } else {
      parsed[key] = value;
    }
  }
  return parsed;
}

function asList(value) {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value : [value];
}

function sha256File(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function sha256Text(text) {
  return crypto.createHash("sha256").update(String(text)).digest("hex");
}

function loadData(file) {
  const text = fs.readFileSync(file, "utf8");
  if (path.extname(file).toLowerCase() === ".json") return JSON.parse(text);
  return yaml.load(text);
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function writeYaml(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, yaml.dump(value, { noRefs: true, lineWidth: 140 }), "utf8");
  if (fs.existsSync(file)) fs.unlinkSync(file);
  fs.renameSync(tmp, file);
}

function resolveExisting(baseDir, value, label = "file") {
  if (!value) throw new Error(`${label} is required`);
  const resolved = path.isAbsolute(value) ? path.resolve(value) : path.resolve(baseDir, value);
  if (!fs.existsSync(resolved)) throw new Error(`${label} not found: ${resolved}`);
  return resolved;
}

function relativeTo(baseDir, file) {
  const rel = path.relative(baseDir, path.resolve(file));
  return rel && !rel.startsWith("..") && !path.isAbsolute(rel)
    ? rel.replace(/\\/g, "/")
    : path.resolve(file).replace(/\\/g, "/");
}

function now() {
  return new Date().toISOString();
}

function statePath(changeDir) {
  return path.join(path.resolve(changeDir), "LIFECYCLE-STATE.yaml");
}

function loadState(changeDir) {
  return loadData(resolveExisting(changeDir, statePath(changeDir), "lifecycle state"));
}

function saveState(changeDir, state) {
  state.updated_at = now();
  writeYaml(statePath(changeDir), state);
}

module.exports = {
  PLUGIN_ROOT,
  yaml,
  parseArgs,
  asList,
  sha256File,
  sha256Text,
  loadData,
  writeJson,
  writeYaml,
  resolveExisting,
  relativeTo,
  now,
  statePath,
  loadState,
  saveState,
};
