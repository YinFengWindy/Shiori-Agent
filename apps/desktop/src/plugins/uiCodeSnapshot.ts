import { createHash } from "node:crypto";
import { readFile, readdir, realpath } from "node:fs/promises";
import { extname, join } from "node:path";

/** Digests every initial JavaScript file, including chunks not yet imported by the browser. */
export async function snapshotPluginUiCode(root: string) {
  const hashes = new Map<string, string>();
  const visit = async (directory: string) => {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      // Links do not expand the code set: contained targets are found at their real paths.
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) await visit(path);
      else if (entry.isFile() && [".js", ".mjs"].includes(extname(entry.name))) {
        hashes.set(await realpath(path), digest(await readFile(path)));
      }
    }
  };
  await visit(root);
  return hashes;
}

function digest(bytes: Uint8Array) {
  return createHash("sha256").update(bytes).digest("hex");
}

/** Rejects changed and newly added code before those bytes can reach the renderer. */
export function matchesPluginUiCode(snapshot: ReadonlyMap<string, string>, path: string, bytes: Uint8Array) {
  return snapshot.get(path) === digest(bytes);
}
