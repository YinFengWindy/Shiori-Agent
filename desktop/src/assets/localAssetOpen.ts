import type { LocalAssetRegistry } from "./localAssetRegistry.js";
import type { LocalAssetOpenResult } from "./shared.js";

/** Opens an authorized local asset through an injected operating-system boundary. */
export async function openGrantedLocalAsset(
  registry: LocalAssetRegistry,
  value: string,
  openPath: (path: string) => Promise<string>,
): Promise<LocalAssetOpenResult> {
  const grant = registry.resolveReference(value);
  if (!grant) {
    return { ok: false, error: "attachment is not authorized" };
  }
  const error = await openPath(grant.canonicalPath);
  return error ? { ok: false, error } : { ok: true, error: null };
}
