import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import process from "node:process";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";
import { buildPlugin } from "./build-plugin.mjs";
import { createPlugin } from "./new-plugin.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const python = join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const run = promisify(execFile);
const pythonPaths = ["packages/sdk/python", "packages/shiori-host-testing/src", "apps/backend", "."].map((path) => join(repository, path));

test("invalid ids and existing directories cannot overwrite a plugin", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "plugin-scaffold-refusal-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await assert.rejects(createPlugin({ id: "../outside", root }), /identifier/);
  const plugin = await createPlugin({ id: "existing_demo", root });
  await writeFile(join(plugin, "README.md"), "User content", "utf8");
  await assert.rejects(createPlugin({ id: "existing_demo", ui: true, root }), { code: "EEXIST" });
  assert.equal(await readFile(join(plugin, "README.md"), "utf8"), "User content");
  await assert.rejects(createPlugin({ id: "chat", root }), /保留|reserved|宿主/i);
  assert.deepEqual(await readdir(join(root, "plugins")), ["existing_demo"]);
});

for (const ui of [false, true]) {
  test(`generated ${ui ? "UI" : "backend"} package builds and survives the real host lifecycle`, { timeout: 120_000 }, async (t) => {
    const root = await mkdtemp(join(tmpdir(), "plugin-scaffold-contract-"));
    t.after(() => rm(root, { recursive: true, force: true }));
    const id = ui ? "scaffold_ui_demo" : "scaffold_backend_demo";
    const plugin = await createPlugin({ id, ui, root });
    const env = { ...process.env, PYTHONUTF8: "1", PYTHONPATH: [root, ...pythonPaths].join(delimiter) };
    const options = { cwd: repository, env, timeout: 90_000, maxBuffer: 4 * 1024 * 1024 };
    await run(python, ["-m", "scripts.gen_plugin_rpc", "--plugin", plugin, "--check"], options);
    await run(python, ["-m", "pytest", "-q", "-c", join(plugin, "pyproject.toml"), join(plugin, "tests")], { ...options, cwd: root });
    await run("uv", ["build", "--wheel", "--out-dir", join(root, "wheels"), plugin], options);
    assert.equal((await readdir(join(root, "wheels"))).filter((name) => name.endsWith(".whl")).length, 1);
    const built = await buildPlugin({ plugin, output: join(root, "output") });
    const validate = "from pathlib import Path; import sys; from desktop_bridge.runtime.plugin_package_archive import validate_package_zip; print(validate_package_zip(Path(sys.argv[1])).manifest.id)";
    assert.equal((await run(python, ["-c", validate, built.archive], options)).stdout.trim(), id);
    await run(python, ["-m", "scripts.verify_plugin_contracts", "--plugin-dir", plugin, "--profile", "rpc", "--output", join(root, "contract.json")], options);
    if (ui) {
      await symlink(join(repository, "node_modules"), join(root, "node_modules"), process.platform === "win32" ? "junction" : "dir");
      const config = { compilerOptions: { target: "ES2022", module: "ESNext", moduleResolution: "bundler", jsx: "react-jsx", strict: true, skipLibCheck: true, noEmit: true, types: ["node", "react", "react-dom"] }, include: ["plugins/**/*.ts", "plugins/**/*.tsx"] };
      await writeFile(join(root, "tsconfig.json"), JSON.stringify(config), "utf8");
      await run(process.execPath, [join(repository, "scripts/check_plugin_rpc.mjs"), "--plugin", plugin], options);
      await run(process.execPath, [join(repository, "node_modules/typescript/bin/tsc"), "-p", join(root, "tsconfig.json")], options);
      await run(process.execPath, [join(repository, "node_modules/tsx/dist/cli.mjs"), "--tsconfig", join(root, "tsconfig.json"), "--test", join(plugin, "ui/index.test.tsx")], { ...options, cwd: root });
    }
  });
}
