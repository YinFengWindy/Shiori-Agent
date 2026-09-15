import { createHash } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import { resolve } from "node:path";

/** Verifies the authoritative backend content snapshot before any renderer resource grant. */
export async function snapshotPluginUiCode(root: string, approved: unknown) {
  if (!approved || typeof approved !== "object" || Array.isArray(approved)) throw new Error("Missing approved plugin content snapshot");
  const hashes = new Map<string, string>();
  for (const [path, expected] of Object.entries(approved)) {
    if (typeof expected !== "string" || !/^[a-f0-9]{64}$/.test(expected) || path.split("/").some((part) => !part || part === "." || part === ".." || /[\\:]/.test(part))) throw new Error("Invalid approved plugin content snapshot");
    const requested = resolve(root, ...path.split("/"));
    const canonical = await realpath(requested);
    if (canonical !== requested || digest(await readFile(canonical)) !== expected) throw new Error("Plugin content changed after approval; restart the application and confirm trust again");
    hashes.set(canonical, expected);
  }
  return hashes;
}

function digest(bytes: Uint8Array) {
  return createHash("sha256").update(bytes).digest("hex");
}

/** Rejects changed and newly added resources before those bytes can reach the renderer. */
export function matchesPluginUiCode(snapshot: ReadonlyMap<string, string>, path: string, bytes: Uint8Array) {
  return snapshot.get(path) === digest(bytes);
}
