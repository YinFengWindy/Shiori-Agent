import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";
import { buildPlugin } from "./build-plugin.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("independent ZIP builds preserve peers and pass the actual host package validator", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "build-plugin-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = join(root, "source"), output = join(root, "output");
  const files = {
    "manifest.yaml": "api: 2\npackage_contract: 1\ndistribution: external\nid: independent_demo\nversion: '1.0.0'\nruntime_api: '>=3.1.1 <4.0.0'\nentry: backend/plugin.py\ncapabilities: []\npeer_dependencies: {react: '>=19.2.0 <20.0.0', react-dom: '>=19.2.0 <20.0.0'}\nrenderer:\n  ui: {entry: renderer/ui.mjs, css: [renderer/ui.css]}\nassets: [assets/label.txt]\n",
    "backend/plugin.py": "from .helper import LABEL\nasync def setup(ctx):\n    pass\n",
    "backend/helper.py": "LABEL = 'self contained'\n",
    "backend/__pycache__/helper.pyc": "not shipped",
    "backend/.venv/runtime.txt": "not shipped",
    "tests/test_plugin.py": "not shipped",
    ".env": "not shipped",
    "ui/index.tsx": "import React from 'react'; import { PluginBridgeError } from '@yinfengwindy/shiori-sdk'; import './style.css'; export default {pluginId: 'independent_demo', settingsSection:{kind:'component',label:'Independent',component:()=><button onClick={()=>{throw new PluginBridgeError('example','example')}}>Hello</button>}};",
    "ui/style.css": ".independent-demo { display: flex; }",
    "assets/label.txt": "resource",
    "README.md": "# Independent demo\n",
    "LICENSE-MIT": "Fixture license\n",
    "docs/usage.md": "Usage\n",
  };
  for (const [name, content] of Object.entries(files)) {
    const target = join(source, name);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, content, "utf8");
  }
  const built = await buildPlugin({ plugin: source, output });
  const first = await readFile(built.archive);
  assert.equal((await buildPlugin({ plugin: source, output })).sha256, built.sha256);
  assert.deepEqual(await readFile(built.archive), first);
  const python = join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const script = "import json, sys\nfrom zipfile import ZipFile\nfrom agent.plugin_host.package_archive import validate_package_zip\nfrom pathlib import Path\np = validate_package_zip(Path(sys.argv[1]))\nwith ZipFile(sys.argv[1]) as z:\n print(json.dumps({'id':p.manifest.id,'names':z.namelist(),'ui':z.read('renderer/ui.mjs').decode()}))\n";
  const { stdout } = await promisify(execFile)(python, ["-c", script, built.archive], { cwd: repository });
  const actual = JSON.parse(stdout);
  assert.equal(actual.id, "independent_demo");
  assert.deepEqual(actual.names.sort(), ["README.md", "LICENSE-MIT", "assets/label.txt", "backend/helper.py", "backend/plugin.py", "docs/usage.md", "manifest.yaml", "renderer/ui.css", "renderer/ui.mjs"].sort());
  assert.match(actual.ui, /from ["']@yinfengwindy\/shiori-sdk["']/);
  assert.match(actual.ui, /from ["']react\/jsx-runtime["']/);
  assert.doesNotMatch(actual.ui, /react\.production|react\.development/);
  await writeFile(join(source, "manifest.yaml"), files["manifest.yaml"].replace("distribution: external", "distribution: builtin"), "utf8");
  await assert.rejects(buildPlugin({ plugin: source, output }), /ZIP sources require/);
});
