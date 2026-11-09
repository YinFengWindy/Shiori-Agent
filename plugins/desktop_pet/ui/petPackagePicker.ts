import type { NativeFilePickerOptions, PluginHostServices } from "@yinfengwindy/shiori-sdk";

/** Returns a private staged ZIP path or null when native selection is cancelled. */
export async function pickPetPackageFile(pickFiles: PluginHostServices["pickFiles"], options: NativeFilePickerOptions) {
  const [source] = await pickFiles(options);
  return source ?? null;
}
