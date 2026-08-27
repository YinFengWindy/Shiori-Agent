import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const developmentRepositoryRoot = resolve(moduleDirectory, "..", "..", "..");

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
  const workspacePath = resolveDesktopWorkspacePath(homePath);
  const configPath = resolveDesktopConfigPath(workspacePath);
  if (!packaged) {
    const backendRoot = resolve(repositoryRoot, "apps", "backend");
    return {
      bridge: {
        executable: resolve(repositoryRoot, ".venv", "Scripts", "python.exe"),
        args: buildBridgeArgs(["main.py"], workspacePath, configPath),
        cwd: backendRoot,
      },
      configPath,
      configTemplatePath: resolve(repositoryRoot, "config", "examples", "config.example.toml"),
      workspacePath,
    };
  }

  const resourcesPath = dirname(appPath);
  const runtimeDirectory = resolve(resourcesPath, "runtime");
  return {
    bridge: {
      executable: resolve(runtimeDirectory, "shiori-runtime.exe"),
      args: buildBridgeArgs([], workspacePath, configPath),
      cwd: runtimeDirectory,
    },
    configPath,
    configTemplatePath: resolve(resourcesPath, "config.example.toml"),
    workspacePath,
  };
}

/** Resolves the single writable workspace owned by the desktop runtime. */
export function resolveDesktopWorkspacePath(homePath: string): string {
  return resolve(homePath, ".shiori", "workspace");
}

/** Resolves the only configuration file consumed by the desktop runtime. */
export function resolveDesktopConfigPath(workspacePath: string): string {
  return resolve(workspacePath, "config.toml");
}

function buildBridgeArgs(prefix: string[], workspacePath: string, configPath: string): string[] {
  return [...prefix, "bridge", "--workspace", workspacePath, "--config", configPath];
}

/** Creates the user-owned config file once, preserving it across upgrades and uninstalls. */
export function ensureDesktopRuntimeConfig(paths: DesktopRuntimePaths): void {
  if (existsSync(paths.configPath)) {
    return;
  }
  mkdirSync(dirname(paths.configPath), { recursive: true });
  copyFileSync(
    paths.configTemplatePath,
    paths.configPath,
  );
}
