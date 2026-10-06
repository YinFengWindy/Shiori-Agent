import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { preparePyinstallerInvocation } from "./pyinstaller-invocation.mjs";

const repository = fileURLToPath(new URL("../../../", import.meta.url));
const python = join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const largeArgs = ["-m", "PyInstaller", "--noconfirm",
  ...Array.from({ length: 2200 }, (_, index) => ["--hidden-import", `shiori_sdk.implicit_namespace_${index}.module`]).flat(),
  "--paths", "C:\\项目 with spaces\\literal $() `quotes` & %DATA% \\",
  "--name", "音声 \"quoted\" \\ literal", "entry with spaces.py"];

async function fixture(t) {
  const directory = await mkdtemp(join(tmpdir(), "shiori freeze 参数 with spaces "));
  t.after(() => rm(directory, { recursive: true, force: true }));
  return directory;
}

test("oversized argument vectors round-trip as UTF-8 JSON while the native command stays short", async (t) => {
  const directory = await fixture(t);
  const invocation = await preparePyinstallerInvocation(largeArgs, directory);
  assert.ok(largeArgs.join(" ").length > 32767);
  assert.equal(invocation.pythonArgs.length, 1);
  assert.ok(invocation.pythonArgs.join(" ").length < 1000);
  assert.deepEqual(JSON.parse(await readFile(invocation.argumentsFile, "utf8")), largeArgs.slice(2));
  await assert.rejects(preparePyinstallerInvocation(["-m", "different_module"], directory), /Expected a Python -m PyInstaller/);
});

test("the generated launcher calls PyInstaller.run with the exact complete vector", { skip: !existsSync(python) }, async (t) => {
  const directory = await fixture(t);
  const invocation = await preparePyinstallerInvocation(largeArgs, directory);
  const stub = join(invocation.directory, "PyInstaller");
  await mkdir(stub);
  await writeFile(join(stub, "__init__.py"), "", "utf8");
  await writeFile(join(stub, "__main__.py"), `import json
from pathlib import Path
def run(args):
    Path(__file__).with_name("received.json").write_text(json.dumps(args), encoding="utf-8")
`, "utf8");
  const child = spawn(python, invocation.pythonArgs, { cwd: directory, stdio: ["ignore", "pipe", "pipe"] });
  const errors = [];
  child.stderr.on("data", (chunk) => errors.push(chunk));
  const code = await new Promise((done, reject) => { child.once("error", reject); child.once("exit", done); });
  assert.equal(code, 0, Buffer.concat(errors).toString("utf8"));
  assert.deepEqual(JSON.parse(await readFile(join(stub, "received.json"), "utf8")), largeArgs.slice(2));
});
