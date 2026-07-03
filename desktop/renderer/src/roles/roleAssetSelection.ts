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

/** Toggle a single-select asset choice. Clicking the selected asset clears the slot. */
export function getNextRoleAssetSelection(
  currentSelectedPath: string,
  clickedPath: string,
): string {
  return currentSelectedPath === clickedPath ? "" : clickedPath;
}
