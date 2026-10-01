import type { NativeFilePickerOptions, PluginHostServices } from "@shiori/sdk";

/** Pet package format and staging policy belongs to this plugin. */
export const petPackagePickerOptions: NativeFilePickerOptions = {
  namespace: "desktop_pet-pets",
  filters: [{ name: "Codex Pet Package", extensions: ["zip"] }],
  multiple: false,
  maxFileBytes: 32 * 1024 * 1024,
};

/** Returns a private staged ZIP path or null when native selection is cancelled. */
export async function pickPetPackageFile(pickFiles: PluginHostServices["pickFiles"]) {
  const [source] = await pickFiles(petPackagePickerOptions);
  return source ?? null;
}
