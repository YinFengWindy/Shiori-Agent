/** Resolve which asset should be highlighted in the asset library for the current mode. */
export function getSelectedRoleAssetPath(
  selectionMode: "avatar" | "chat-background",
  selectedAvatarAsset: string,
  selectedChatBackground: string,
): string {
  if (selectionMode === "avatar") {
    return selectedAvatarAsset;
  }
  return selectedChatBackground;
}

/** Resolve the next selected asset path for single-select modes. */
export function getNextRoleAssetSelection(
  currentSelectedPath: string,
  clickedPath: string,
): string {
  return currentSelectedPath === clickedPath ? currentSelectedPath : clickedPath;
}
