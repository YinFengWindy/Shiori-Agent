import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { collectSdkRuntimeModules } from "./runtime-plugin-modules.mjs";
import { assertRuntimeHiddenImports } from "./runtime-pyinstaller.mjs";
import { preparePyinstallerInvocation } from "./pyinstaller-invocation.mjs";

const repository = fileURLToPath(new URL("../../../", import.meta.url));
const { values } = parseArgs({ options: { output: { type: "string" } } });
const output = values.output ? resolve(values.output) : await mkdtemp(join(tmpdir(), "shiori-sdk-runtime-"));
await mkdir(output, { recursive: true });
const sdkRoot = join(repository, "packages/sdk/python/shiori_sdk");
const modules = await collectSdkRuntimeModules(sdkRoot);
const python = join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const entry = join(output, "sdk_runtime_probe.py");
const targets = ["shiori_sdk.files.audio", "shiori_sdk.files.staging", "shiori_sdk.local_http"];
await writeFile(entry, `import importlib
import importlib.util
import json
import sys
from pathlib import Path

assert getattr(sys, "frozen", False)
root = Path(sys._MEIPASS).resolve()
loaded = {}
for name in json.loads(sys.argv[1]):
    module = importlib.import_module(name)
    path = Path(module.__file__).resolve()
    assert path.is_relative_to(root), (name, str(path), str(root))
    loaded[name] = str(path)
assert importlib.util.find_spec("shiori_sdk.testing") is None
print(json.dumps({"frozen": True, "loaded": loaded, "testing_absent": True}))
`, "utf8");
const args = [
  "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "sdk-runtime-probe",
  "--distpath", join(output, "dist"), "--workpath", join(output, "build"), "--specpath", output,
  "--paths", join(repository, "packages/sdk/python"), "--exclude-module", "shiori_sdk.testing",
  ...modules.flatMap((name) => ["--hidden-import", name]), entry,
];
assertRuntimeHiddenImports(args, modules);
await writeFile(join(output, "collection.json"), JSON.stringify({ modules, args }, null, 2), "utf8");

async function run(executable, arguments_, log, env = process.env) {
  const child = spawn(executable, arguments_, { cwd: output, env, stdio: ["ignore", "pipe", "pipe"] });
  const chunks = [];
  child.stdout.on("data", (chunk) => chunks.push(chunk));
  child.stderr.on("data", (chunk) => chunks.push(chunk));
  const code = await new Promise((done, reject) => { child.once("error", reject); child.once("exit", done); });
  await writeFile(join(output, log), Buffer.concat(chunks));
  assert.equal(code, 0, `${executable} failed; inspect ${join(output, log)}`);
}

console.log(`Freezing ${modules.length} runtime SDK modules. Evidence: ${output}`);
// Exercise the production argument transport with the actual PyInstaller entry point.
const invocation = await preparePyinstallerInvocation(args, join(output, "invocation"));
await run(python, invocation.pythonArgs, "freeze.log");
const env = { ...process.env };
// The executable must satisfy dynamic imports from its own archive, not source.
delete env.PYTHONPATH;
delete env.PYTHONHOME;
const executable = join(output, "dist/sdk-runtime-probe", process.platform === "win32" ? "sdk-runtime-probe.exe" : "sdk-runtime-probe");
await run(executable, [JSON.stringify(targets)], "probe.json", env);
console.log(await readFile(join(output, "probe.json"), "utf8"));
console.log(`PASS frozen runtime SDK dynamic imports; testing excluded. Evidence: ${output}`);
