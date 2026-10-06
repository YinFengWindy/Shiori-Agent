import { delimiter, join } from "node:path";

/** Assemble the actual frozen-host invocation, including SDK modules used only by external plugins. */
export function createRuntimePyinstallerArgs({
  runtimeRoot, workRoot, backendRoot, stagingRoot, stagedPluginsDir,
  browserRuntime, computerRuntime, repositoryRoot, pluginModules, hostModules, sdkModules,
}) {
  const modules = [...pluginModules, ...hostModules, ...sdkModules];
  const args = [
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "shiori-runtime",
    "--distpath", runtimeRoot, "--workpath", workRoot, "--specpath", workRoot,
    "--paths", backendRoot, "--paths", stagingRoot,
    "--paths", join(repositoryRoot, "packages/sdk/python"),
    // Package admission reads the distribution's direct runtime requirements.
    "--recursive-copy-metadata", "shiori-agent",
    "--exclude-module", "shiori_sdk.testing",
    "--add-data", `${stagedPluginsDir}${delimiter}plugins`,
    "--add-data", `${browserRuntime}${delimiter}native/browser-use`,
    "--add-data", `${computerRuntime}${delimiter}native/computer-use`,
    "--add-data", `${join(backendRoot, "skills")}${delimiter}skills`,
    "--add-data", `${join(repositoryRoot, "apps", "desktop", "renderer", "src", "chat", "common_emojis.json")}${delimiter}.`,
    "--add-data", `${join(repositoryRoot, "config.example.toml")}${delimiter}.`,
    ...modules.flatMap((name) => ["--hidden-import", name]),
    join(backendRoot, "main.py"),
  ];
  assertRuntimeHiddenImports(args, modules);
  return args;
}

/** Fail before freezing if a collected host, builtin or SDK module is absent from the final arguments. */
export function assertRuntimeHiddenImports(args, modules) {
  const included = new Set(args.filter((value, index) => index > 0 && args[index - 1] === "--hidden-import"));
  const missing = modules.filter((name) => !included.has(name));
  if (missing.length) throw new Error(`PyInstaller hidden imports missing: ${missing.join(", ")}`);
}
