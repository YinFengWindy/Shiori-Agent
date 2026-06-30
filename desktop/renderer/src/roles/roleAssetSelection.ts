/** Resolve which asset should be highlighted in the asset library for the current mode. */
export function getSelectedRoleAssetPath(
  selectionMode: "avatar" | "featured",
  selectedAvatarAsset: string,
  selectedFeaturedImage: string,
  fallbackAssetPath: string,
): string {
  if (selectionMode === "avatar") {
    return selectedAvatarAsset || fallbackAssetPath;
  }
  return selectedFeaturedImage || fallbackAssetPath;
}
