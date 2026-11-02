/** One pet package as `desktop_pet.pets.list` reports it. */
export type PetPackageRow = {
  id: string;
  displayName: string;
  /** Opaque asset URL, or empty when the host granted none (missing file). */
  previewUrl: string;
};

export type PetPackages = {
  selectedPackageId: string | null;
  packages: PetPackageRow[];
};

export const noPetPackages: PetPackages = { selectedPackageId: null, packages: [] };

/**
 * Parses a `pets.list` response.
 *
 * Split from the component so the parsing is testable without a DOM, and
 * because it is the boundary where this plugin stops trusting a payload: the
 * rows cross the bridge as plain data, and a malformed one must degrade to
 * "no packages" rather than render a row with `undefined` in it.
 *
 * `preview_abs` becomes a URL here rather than in the component: the raw path
 * is a filesystem path the renderer must not display or keep, and
 * `resolveAssetUrl` is the only thing that turns it into something showable.
 */
export function readPetPackages(
  value: unknown,
  resolveAssetUrl: (path: string) => string,
): PetPackages {
  if (!value || typeof value !== "object") return noPetPackages;
  const source = value as { selected_package_id?: unknown; packages?: unknown };
  const rows = Array.isArray(source.packages) ? source.packages : [];
  const packages: PetPackageRow[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const { id, display_name: displayName, preview_abs: previewAbs } = row as Record<string, unknown>;
    if (typeof id !== "string" || !id) continue;
    packages.push({
      id,
      displayName: typeof displayName === "string" ? displayName : id,
      previewUrl: typeof previewAbs === "string" && previewAbs ? resolveAssetUrl(previewAbs) : "",
    });
  }
  const selected = source.selected_package_id;
  return {
    selectedPackageId: typeof selected === "string" && selected ? selected : null,
    packages,
  };
}
