import { isAbsolute } from "node:path";

export type PluginRpcMethod = {
  method: string;
  remoteName: string;
};

export type PluginOverlayContribution = {
  id: string;
  kind: "overlay";
  entrypoint: string;
  width: number;
  height: number;
  transparent: boolean;
  alwaysOnTop: boolean;
  skipTaskbar: boolean;
  resizable: boolean;
  frame: boolean;
};

export type InstalledDesktopPlugin = {
  pluginId: string;
  name: string;
  packageDir: string;
  enabled: boolean;
  capabilities: ReadonlySet<string>;
  rpcMethods: readonly PluginRpcMethod[];
  contributions: readonly PluginOverlayContribution[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function requiredString(value: Record<string, unknown>, key: string): string | null {
  const candidate = value[key];
  return typeof candidate === "string" && candidate.trim() ? candidate.trim() : null;
}

function optionalBoolean(value: Record<string, unknown>, key: string, fallback: boolean): boolean | null {
  const candidate = value[key];
  if (candidate === undefined) return fallback;
  return typeof candidate === "boolean" ? candidate : null;
}

function parseRpcMethods(value: unknown): PluginRpcMethod[] | null {
  if (!Array.isArray(value)) return null;
  const methods: PluginRpcMethod[] = [];
  const publicNames = new Set<string>();
  for (const item of value) {
    if (!isRecord(item)) return null;
    const method = requiredString(item, "method");
    const remoteName = requiredString(item, "remote_name");
    if (!method || !remoteName || publicNames.has(method)) return null;
    publicNames.add(method);
    methods.push({ method, remoteName });
  }
  return methods;
}

function parseContributions(value: unknown): PluginOverlayContribution[] | null {
  if (!Array.isArray(value)) return null;
  const contributions: PluginOverlayContribution[] = [];
  const ids = new Set<string>();
  for (const item of value) {
    if (!isRecord(item)) return null;
    const id = requiredString(item, "id");
    const entrypoint = requiredString(item, "entrypoint");
    const width = item.width;
    const height = item.height;
    if (
      !id
      || !entrypoint
      || item.kind !== "overlay"
      || ids.has(id)
      || !Number.isInteger(width)
      || !Number.isInteger(height)
    ) return null;
    const transparent = optionalBoolean(item, "transparent", false);
    const alwaysOnTop = optionalBoolean(item, "always_on_top", false);
    const skipTaskbar = optionalBoolean(item, "skip_taskbar", true);
    const resizable = optionalBoolean(item, "resizable", false);
    const frame = optionalBoolean(item, "frame", false);
    if ([transparent, alwaysOnTop, skipTaskbar, resizable, frame].includes(null)) return null;
    ids.add(id);
    contributions.push({
      id,
      kind: "overlay",
      entrypoint,
      width: width as number,
      height: height as number,
      transparent: transparent as boolean,
      alwaysOnTop: alwaysOnTop as boolean,
      skipTaskbar: skipTaskbar as boolean,
      resizable: resizable as boolean,
      frame: frame as boolean,
    });
  }
  return contributions;
}

/** Parses bridge data into the strict subset consumed by the Electron plugin host. */
export function parseInstalledDesktopPlugins(value: unknown): InstalledDesktopPlugin[] {
  if (!Array.isArray(value)) return [];
  const plugins: InstalledDesktopPlugin[] = [];
  for (const item of value) {
    if (!isRecord(item) || !isRecord(item.manifest)) continue;
    const pluginId = requiredString(item, "plugin_id");
    const packageDir = requiredString(item, "package_dir");
    const name = requiredString(item.manifest, "name");
    const manifestPluginId = requiredString(item.manifest, "plugin_id");
    if (
      !pluginId
      || pluginId !== manifestPluginId
      || !packageDir
      || !isAbsolute(packageDir)
      || !name
      || typeof item.enabled !== "boolean"
      || !Array.isArray(item.manifest.capabilities)
      || !item.manifest.capabilities.every((capability) => typeof capability === "string")
    ) continue;
    const rpcMethods = parseRpcMethods(item.manifest.rpc_methods);
    const contributions = parseContributions(item.manifest.desktop_contributions);
    if (!rpcMethods || !contributions) continue;
    const capabilities = new Set(item.manifest.capabilities as string[]);
    if (rpcMethods.length > 0 && !capabilities.has("plugin.rpc")) continue;
    if (contributions.length > 0 && !capabilities.has("desktop.overlay")) continue;
    plugins.push({
      pluginId,
      name,
      packageDir,
      enabled: item.enabled,
      capabilities,
      rpcMethods,
      contributions,
    });
  }
  return plugins;
}
