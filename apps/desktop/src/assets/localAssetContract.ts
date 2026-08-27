/** Shared renderer-safe local asset protocol and size limits. */
export const localAssetScheme = "shiori-asset";
export const localAssetAuthority = "local";
export const maxLocalAssetBytes = 32 * 1024 * 1024;
export const unavailableLocalAssetUrl = `${localAssetScheme}://${localAssetAuthority}/unavailable`;
