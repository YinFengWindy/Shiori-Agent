import { isAbsolute } from "node:path";
import type { NativeFilePathPickerOptions } from "@yinfengwindy/shiori-sdk/contract";
import type { OpenDialogOptions, OpenDialogReturnValue } from "electron";
import { normalizeFilePathPickerOptions, normalizeFilePickerOptions } from "../assets/filePickerContract.js";
import { admitPickedFilePaths } from "../assets/pickedFilePaths.js";
import { stagePickedFiles } from "../assets/pickedFileStaging.js";

type ShowOpenDialog = (options: OpenDialogOptions) => Promise<OpenDialogReturnValue>;

function fileDialogOptions(policy: NativeFilePathPickerOptions): OpenDialogOptions {
  return { properties: policy.multiple ? ["openFile", "multiSelections"] : ["openFile"], filters: policy.filters };
}

/** Opens a constrained native dialog and stages only the paths it returned. */
export async function pickNativeFiles(options: unknown, importsRoot: string, showOpenDialog: ShowOpenDialog) {
  const policy = normalizeFilePickerOptions(options);
  const selected = await showOpenDialog(fileDialogOptions(policy));
  if (selected.canceled) return [];
  return stagePickedFiles(selected.filePaths, importsRoot, policy);
}

/** Opens a constrained native dialog and returns the admitted original paths, copying nothing. */
export async function pickNativeFilePaths(options: unknown, showOpenDialog: ShowOpenDialog) {
  const policy = normalizeFilePathPickerOptions(options);
  const selected = await showOpenDialog(fileDialogOptions(policy));
  if (selected.canceled) return [];
  return admitPickedFilePaths(selected.filePaths, policy);
}

/** Opens a native directory dialog that may create a directory; `null` when cancelled. */
export async function pickNativeDirectory(showOpenDialog: ShowOpenDialog) {
  const selected = await showOpenDialog({ properties: ["openDirectory", "createDirectory"] });
  const [directory] = selected.filePaths;
  if (selected.canceled || !directory) return null;
  if (!isAbsolute(directory)) throw new Error("选择的目录无效");
  return directory;
}
