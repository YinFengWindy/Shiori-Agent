import { lstat } from "node:fs/promises";
import type { NativeFilePathPickerOptions } from "@yinfengwindy/shiori-sdk/contract";
import { assertPickedSelection, normalizeFilePathPickerOptions } from "./filePickerContract.js";

/**
 * Admits files returned by the native dialog by their original paths: the
 * same count, extension and per-file size policy as staging, checked by
 * metadata only — nothing is read, copied or granted as media.
 */
export async function admitPickedFilePaths(sourcePaths: readonly string[], options: NativeFilePathPickerOptions) {
  const policy = normalizeFilePathPickerOptions(options);
  assertPickedSelection(sourcePaths, policy);
  for (const source of sourcePaths) {
    const stats = await lstat(source);
    if (!stats.isFile()) throw new Error("选择的路径不是普通文件");
    if (stats.size > policy.maxFileBytes) throw new Error("选择的文件超过大小限制");
  }
  return [...sourcePaths];
}
