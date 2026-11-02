import { existsSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { builtinPluginDirectories, readPluginManifest, PLUGIN_RENDERER_SOURCES } from "../../../scripts/plugin-distribution.mjs";

import { frontendExports } from "../../../scripts/plugin-frontend.mjs";

const prefix = "virtual:shiori-builtin-plugins/";

/** Generate imports before bundling, so external source never enters the host graph. */
export async function builtinPluginEntrySource(pluginsRoot, kind) {
  if (!Object.hasOwn(PLUGIN_RENDERER_SOURCES, kind)) throw new Error(`Unknown plugin entry kind: ${kind}`);
  const entries = [];
  for (const directory of await builtinPluginDirectories(pluginsRoot)) {
    const manifest = await readPluginManifest(directory);
    const exports = await frontendExports(directory, manifest);
    if (exports.length) {
      if (exports.includes(kind)) entries.push({ path: join(directory, manifest.frontend.entry), exportName: kind });
    } else {
      // Temporary P7-4 source adapter, never a compatibility path for old APIs.
      const path = join(directory, PLUGIN_RENDERER_SOURCES[kind]);
      if (existsSync(path)) entries.push({ path, exportName: "default" });
    }
  }
  return {
    paths: entries.map(({ path }) => path),
    code: [
      ...entries.map(({ path }, index) => `import * as entry${index} from ${JSON.stringify(path.replaceAll("\\", "/"))};`),
      `export default {${entries.map(({ path, exportName }, index) => `${JSON.stringify(path)}: {default:entry${index}.${exportName}}`).join(",")}};`,
    ].join("\n"),
  };
}

/** Vite boundary for the three host-owned static contribution registries. */
export function builtinPluginEntries(pluginsRoot) {
  const ids = Object.keys(PLUGIN_RENDERER_SOURCES).map((kind) => prefix + kind);
  return {
    name: "shiori-builtin-plugin-entries",
    resolveId(id) { if (ids.includes(id)) return `\0${id}`; },
    async load(id) {
      if (!ids.some((candidate) => id === `\0${candidate}`)) return;
      const kind = id.slice(id.lastIndexOf("/") + 1);
      const result = await builtinPluginEntrySource(pluginsRoot, kind);
      for (const path of result.paths) this.addWatchFile(path);
      return result.code;
    },
    configureServer(server) {
      // Watch inventory changes here: addWatchFile would make Vite resolve this
      // directory as an import of the virtual module during client transforms.
      server.watcher.add(pluginsRoot);
      const changed = (path, includeEntries = false) => {
        const parts = relative(resolve(pluginsRoot), resolve(path)).replaceAll("\\", "/").split("/");
        const manifestChanged = parts.length === 2 && parts[1] === "manifest.yaml";
        const entryChanged = includeEntries && /\.[cm]?[jt]sx?$/.test(parts.at(-1));
        if (parts[0] === ".." || (!manifestChanged && !entryChanged)) return;
        for (const id of ids) {
          const module = server.moduleGraph.getModuleById(`\0${id}`);
          if (module) server.moduleGraph.invalidateModule(module);
        }
        server.ws.send({ type: "full-reload" });
      };
      const shapeChanged = (path) => changed(path, true);
      const listeners = { add: shapeChanged, change: (path) => changed(path), unlink: shapeChanged };
      for (const [event, listener] of Object.entries(listeners)) server.watcher.on(event, listener);
      server.httpServer?.once("close", () => {
        for (const [event, listener] of Object.entries(listeners)) server.watcher.off(event, listener);
      });
    },
  };
}
