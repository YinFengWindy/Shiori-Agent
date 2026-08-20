import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const developmentRepositoryRoot = resolve(moduleDirectory, "..", "..");

/** Command used to start the Python bridge in either desktop runtime mode. */
export type DesktopBridgeCommand = {
  executable: string;
  args: string[];
  cwd: string;
};

/** Read-only and user-writable paths required by the desktop runtime. */
export type DesktopRuntimePaths = {
  bridge: DesktopBridgeCommand;
  configPath: string;
  configTemplatePath: string;
  legacyConfigPath?: string;
  workspacePath: string;
};

type ResolveDesktopRuntimePathsOptions = {
  packaged: boolean;
  appPath: string;
  homePath: string;
  repositoryRoot?: string;
};

/** Resolves all runtime locations without relying on the current working directory. */
export function resolveDesktopRuntimePaths({
  packaged,
  appPath,
  homePath,
  repositoryRoot = developmentRepositoryRoot,
}: ResolveDesktopRuntimePathsOptions): DesktopRuntimePaths {
  const workspacePath = resolve(homePath, ".shiori", "workspace");
  const configPath = resolve(workspacePath, "config.toml");
  if (!packaged) {
    return {
      bridge: {
        executable: resolve(repositoryRoot, ".venv", "Scripts", "python.exe"),
        args: ["main.py", "bridge", "--workspace", workspacePath, "--config", configPath],
        cwd: repositoryRoot,
      },
      configPath,
      configTemplatePath: resolve(repositoryRoot, "config.example.toml"),
      legacyConfigPath: resolve(repositoryRoot, "config.toml"),
      workspacePath,
    };
  }

  const resourcesPath = dirname(appPath);
  const runtimeDirectory = resolve(resourcesPath, "runtime");
  return {
    bridge: {
      executable: resolve(runtimeDirectory, "shiori-runtime.exe"),
      args: ["bridge", "--workspace", workspacePath, "--config", configPath],
      cwd: runtimeDirectory,
    },
    configPath,
    configTemplatePath: resolve(resourcesPath, "config.example.toml"),
    workspacePath,
  };
}

/** Creates the user-owned config file once, preserving it across upgrades and uninstalls. */
export function ensureDesktopRuntimeConfig(paths: DesktopRuntimePaths): void {
  if (existsSync(paths.configPath)) {
    return;
  }
  mkdirSync(dirname(paths.configPath), { recursive: true });
  copyFileSync(
    paths.legacyConfigPath && existsSync(paths.legacyConfigPath)
      ? paths.legacyConfigPath
      : paths.configTemplatePath,
    paths.configPath,
  );
}
