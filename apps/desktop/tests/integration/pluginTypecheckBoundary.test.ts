import assert from "node:assert/strict";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import ts from "typescript";

test("standalone plugin program excludes host sources and rejects the ambient global bridge", () => {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
  const configPath = resolve(root, "plugins/tsconfig.json");
  const config = ts.readConfigFile(configPath, ts.sys.readFile);
  assert.equal(config.error, undefined);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, dirname(configPath));
  assert.deepEqual(parsed.errors, []);
  const probe = resolve(root, "plugins/boundary_probe/surface/ambient.ts");
  const host = ts.createCompilerHost(parsed.options);
  const getSourceFile = host.getSourceFile.bind(host);
  const fileExists = host.fileExists.bind(host);
  host.fileExists = (name) => resolve(name) === probe || fileExists(name);
  host.getSourceFile = (name, languageVersion, onError, shouldCreate) => resolve(name) === probe
    ? ts.createSourceFile(name, 'window.miraDesktop; let bridge: DesktopApi;', languageVersion, true)
    : getSourceFile(name, languageVersion, onError, shouldCreate);
  const program = ts.createProgram([...parsed.fileNames, probe], parsed.options, host);
  const files = program.getSourceFiles().map((file) => file.fileName.replaceAll("\\", "/"));
  assert.ok(files.some((name) => name.endsWith("/plugins/desktop_pet/surface/DesktopPetSurface.tsx")));
  assert.ok(files.some((name) => name.endsWith("/plugins/desktop_pet/surface/DesktopPetSurface.test.tsx")));
  assert.equal(files.some((name) => name.includes("/apps/desktop/")), false, "a host source or ambient declaration leaked into the plugin program");
  const source = program.getSourceFile(probe);
  assert.ok(source);
  const diagnostics = program.getSemanticDiagnostics(source);
  assert.ok(diagnostics.some((entry) => entry.code === 2339), "window.miraDesktop unexpectedly typechecked");
  assert.ok(diagnostics.some((entry) => entry.code === 2304), "DesktopApi unexpectedly exists in the plugin program");
});
