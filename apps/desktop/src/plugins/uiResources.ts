import { randomUUID } from "node:crypto";
import { readFile, realpath, stat } from "node:fs/promises";
import { extname, isAbsolute, relative, resolve, sep } from "node:path";
import { pluginUiPeerExports, pluginUiScheme, type RuntimePluginUi } from "./uiContract.js";
import { matchesPluginUiCode, snapshotPluginUiCode } from "./uiCodeSnapshot.js";

type Grant = { token: string; requested: string; canonical: string; workspace: string; code: ReadonlyMap<string, string> };
const mimeTypes: Record<string, string> = {
  ".mjs": "text/javascript", ".js": "text/javascript", ".css": "text/css",
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
  ".svg": "image/svg+xml", ".gif": "image/gif", ".woff": "font/woff", ".woff2": "font/woff2",
};

function within(root: string, path: string) {
  const child = relative(root, path);
  return child !== "" && !isAbsolute(child) && child !== ".." && !child.startsWith(`..${sep}`);
}

/** Stable package grants preserve relative chunks and CSS assets without granting file access. */
export class PluginUiResources {
  private grants = new Map<string, Grant>();
  // Code identity lives for the app session, independently of current authorization.
  private readonly packages = new Map<string, { identity: string; grant: Grant }>();
  constructor(private readonly workspacePlugins: string) {}

  /** Reconciles grants with the current authoritative backend roster. */
  async admit(rows: unknown): Promise<RuntimePluginUi[]> {
    if (!Array.isArray(rows)) throw new Error("Invalid plugin roster");
    const next = new Map<string, Grant>();
    const result: RuntimePluginUi[] = [];
    for (const row of rows) {
      if (!row || typeof row !== "object" || row.source !== "workspace" || row.state !== "ACTIVE" || !row.enabled) continue;
      if (rows.filter((item) => item?.id === row.id).length !== 1 || !row.renderer?.ui) continue;
      const ui = row.renderer.ui;
      try {
        if (typeof row.id !== "string" || typeof row.directory !== "string" || typeof ui.entry !== "string" || !Array.isArray(ui.css) || !ui.css.every((path: unknown) => typeof path === "string")) throw new Error("Invalid renderer descriptor");
        const workspace = await realpath(this.workspacePlugins);
        const canonical = await realpath(row.directory);
        if (!within(workspace, canonical)) throw new Error("Plugin directory escapes workspace plugins");
        const identity = JSON.stringify([row.directory, canonical, workspace, row.version ?? "", row.content_fingerprint, ui.entry, ui.css]);
        const old = this.packages.get(row.id);
        if (old && old.identity !== identity) throw new Error("Plugin package changed; restart the application to load its new code");
        const grant = old?.grant ?? { token: randomUUID(), requested: row.directory, canonical, workspace, code: await snapshotPluginUiCode(canonical, row.content_hashes) };
        const url = (path: string) => {
          if (!within(canonical, resolve(canonical, path)) || path.includes("\\") || path.split("/").some((part) => !part || part === "." || part === "..")) throw new Error("Plugin resource escapes package");
          if (!grant.code.has(resolve(canonical, path))) throw new Error("Plugin entry is not part of its approved content snapshot");
          return `${pluginUiScheme}://plugin/${grant.token}/${path.split("/").map(encodeURIComponent).join("/")}`;
        };
        result.push({ pluginId: row.id, entry: url(ui.entry), css: ui.css.map(url) });
        this.packages.set(row.id, { identity, grant });
        next.set(row.directory, grant);
      } catch (error) {
        result.push({ pluginId: String(row.id), entry: "", css: [], error: error instanceof Error ? error.message : String(error) });
      }
    }
    this.grants = next;
    return result;
  }

  /** Checks current package and file realpaths before serving an allowed resource format. */
  async load(url: string): Promise<Response> {
    const headers = { "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Type": "text/javascript" };
    const peer = Object.keys(pluginUiPeerExports).find((name) => url === `${pluginUiScheme}://host/${name}.mjs`);
    if (peer) {
      const source = `const peer = globalThis.__shioriPluginPeers[${JSON.stringify(peer)}];\nexport default peer;\n${pluginUiPeerExports[peer].map((name) => `export const ${name} = peer.${name};`).join("\n")}`;
      return new Response(source, { headers });
    }
    try {
      const parsed = new URL(url);
      const [, token, ...segments] = parsed.pathname.split("/").map(decodeURIComponent);
      const grant = [...this.grants.values()].find((item) => item.token === token);
      if (parsed.protocol !== `${pluginUiScheme}:` || parsed.host !== "plugin" || !grant || segments.some((segment) => !segment || segment === "." || segment === ".." || /[\\/]/.test(segment))) return new Response("Plugin resource is not authorized", { status: 403 });
      const path = resolve(grant.requested, ...segments);
      const current = await realpath(path);
      if (await realpath(grant.requested) !== grant.canonical || await realpath(this.workspacePlugins) !== grant.workspace || !within(grant.canonical, current)) return new Response("Plugin resource authorization is stale", { status: 403 });
      const mime = mimeTypes[extname(current)];
      if (!mime || !(await stat(current)).isFile()) return new Response("Unsupported plugin resource", { status: 403 });
      const bytes = await readFile(current);
      if (!matchesPluginUiCode(grant.code, current, bytes)) return new Response("Plugin content changed; restart the application and confirm trust again", { status: 409, statusText: "Plugin content changed; restart required" });
      return new Response(bytes, { headers: { ...headers, "Content-Type": mime } });
    } catch {
      return new Response("Plugin resource is unavailable", { status: 404 });
    }
  }
}
