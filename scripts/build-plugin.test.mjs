import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";
import { buildPlugin } from "./build-plugin.mjs";
import { pathToFileURL } from "node:url";

const peers = { react: ">=19.2.0 <20.0.0", "react-dom": ">=19.2.0 <20.0.0", "@yinfengwindy/shiori-sdk": ">=4.0.0 <5.0.0" };
const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("one frontend artifact carries named contributions without starting their effects", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "frontend-package-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = join(root, "source");
  await mkdir(join(source, "backend"), { recursive: true });
  await writeFile(join(source, "backend/plugin.py"), "async def setup(ctx):\n    pass\n", "utf8");
  await writeFile(join(source, "manifest.yaml"), "api: 4\nsdk: '>=4.0.0'\ndistribution: external\nid: frontend_demo\nversion: '1.0.0'\nentry: backend/plugin.py\nfrontend: {entry: entry.ts}\n", "utf8");
  await writeFile(join(source, "package.json"), JSON.stringify({peerDependencies: peers}), "utf8");
  await writeFile(join(source, "entry.ts"), "import './style.css'; export const ui={pluginId:'frontend_demo'}; export const background={pluginId:'frontend_demo',setup(){throw Error('explicit start only')}}; export const surface={pluginId:'frontend_demo',surface:{component(){return null}}};", "utf8");
  await writeFile(join(source, "style.css"), ".frontend-demo { display: flex; }", "utf8");
  const built = await buildPlugin({ plugin: source, output: join(root, "output") });
  const python = process.env.SHIORI_TEST_PYTHON ?? join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const script = "import json,sys\nfrom pathlib import Path\nfrom zipfile import ZipFile\nfrom agent.plugin_host.package_archive import validate_package_zip\np=validate_package_zip(Path(sys.argv[1]))\nwith ZipFile(sys.argv[1]) as z: z.extractall(sys.argv[2])\nprint(json.dumps({'exports':p.frontend.exports, 'entry':p.manifest.frontend_entry}))";
  const extracted = join(root, "extracted");
  const { stdout } = await promisify(execFile)(python, ["-c", script, built.archive, extracted], { cwd: repository });
  const contract = JSON.parse(stdout);
  assert.deepEqual(contract.exports, ["background", "surface", "ui"]);
  const namespace = await import(pathToFileURL(join(extracted, contract.entry)).href);
  assert.equal(namespace.default, undefined);
  assert.equal(namespace.ui.pluginId, "frontend_demo");
  assert.equal(namespace.surface.surface.component(), null);
  assert.throws(() => namespace.background.setup(), /explicit start only/);
  assert.match(await readFile(join(extracted, "renderer/frontend.css"), "utf8"), /display: flex/);
});

test("independent ZIP builds preserve peers and pass the actual host package validator", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "build-plugin-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = join(root, "source"), output = join(root, "output");
  const files = {
    "package.json": JSON.stringify({peerDependencies: peers}),
    "manifest.yaml": "api: 4\nsdk: '>=4.0.0'\ndistribution: external\nid: independent_demo\nversion: '1.0.0'\nentry: backend/plugin.py\nfrontend: {entry: ui/index.tsx}\nassets: [assets/label.txt]\n",
    "backend/plugin.py": "from .helper import LABEL\nasync def setup(ctx):\n    pass\n",
    "backend/helper.py": "LABEL = 'self contained'\n",
    "backend/__pycache__/helper.pyc": "not shipped",
    "backend/.venv/runtime.txt": "not shipped",
    "tests/test_plugin.py": "not shipped",
    ".env": "not shipped",
    "ui/index.tsx": "import React from 'react'; import { PluginBridgeError } from '@yinfengwindy/shiori-sdk'; import './style.css'; export const ui = {pluginId: 'independent_demo', settingsSection:{kind:'component',label:'Independent',component:()=><button onClick={()=>{throw new PluginBridgeError('example','example')}}>Hello</button>}};",
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
  const python = process.env.SHIORI_TEST_PYTHON ?? join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const script = "import json, sys\nfrom zipfile import ZipFile\nfrom agent.plugin_host.package_archive import validate_package_zip\nfrom pathlib import Path\np = validate_package_zip(Path(sys.argv[1]))\nwith ZipFile(sys.argv[1]) as z:\n print(json.dumps({'id':p.manifest.id,'names':z.namelist(),'ui':z.read('renderer/frontend.mjs').decode()}))\n";
  const { stdout } = await promisify(execFile)(python, ["-c", script, built.archive], { cwd: repository });
  const actual = JSON.parse(stdout);
  assert.equal(actual.id, "independent_demo");
  assert.deepEqual(actual.names.sort(), ["README.md", "LICENSE-MIT", "assets/label.txt", "backend/helper.py", "backend/plugin.py", "docs/usage.md", "manifest.yaml", "renderer/frontend.css", "renderer/frontend.mjs"].sort());
  assert.match(actual.ui, /from ["']@yinfengwindy\/shiori-sdk["']/);
  assert.match(actual.ui, /from ["']react\/jsx-runtime["']/);
  assert.doesNotMatch(actual.ui, /react\.production|react\.development/);
  await writeFile(join(source, "manifest.yaml"), files["manifest.yaml"].replace("distribution: external", "distribution: builtin"), "utf8");
  await assert.rejects(buildPlugin({ plugin: source, output }), /ZIP sources require/);
});
