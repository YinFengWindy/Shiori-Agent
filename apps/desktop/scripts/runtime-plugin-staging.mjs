import { cp, mkdir } from "node:fs/promises";
import { basename, join, relative, sep } from "node:path";
import { builtinPluginDirectories } from "../../../scripts/plugin-distribution.mjs";

/** Stage host-owned packages only, before hidden-import analysis or runtime copying. */
export async function stageBuiltinPlugins(sourceRoot, destination) {
  await mkdir(destination, { recursive: true });
  for (const directory of await builtinPluginDirectories(sourceRoot)) {
    await cp(directory, join(destination, basename(directory)), {
      recursive: true,
      filter: (source) => basename(source) !== "__pycache__"
        && relative(directory, source).split(sep)[0] !== "tests",
    });
  }
}
