import { randomUUID } from "node:crypto";
import { lstat, mkdir, open, realpath, rm } from "node:fs/promises";
import { basename, extname, isAbsolute, join } from "node:path";
import { isLocalAssetInsideRoot } from "./localAssetPolicy.js";
import type { NativeFilePickerOptions } from "@yinfengwindy/shiori-sdk/contract";
import { maxNativeBatchBytes, maxNativeFileCount, normalizeFilePickerOptions } from "./filePickerContract.js";

/** Copies only files returned by the native dialog, without issuing media grants. */
export async function stagePickedFiles(sourcePaths: readonly string[], importsRoot: string, options: NativeFilePickerOptions) {
  const policy = normalizeFilePickerOptions(options);
  if (sourcePaths.length > (policy.multiple ? maxNativeFileCount : 1)) throw new Error("选择的文件数量超过限制");
  if (!sourcePaths.length) return [];
  await mkdir(importsRoot, { recursive: true });
  const root = await realpath(importsRoot);
  const namespace = join(root, policy.namespace);
  await mkdir(namespace, { recursive: true });
  if ((await lstat(namespace)).isSymbolicLink() || !isLocalAssetInsideRoot(await realpath(namespace), root)) {
    throw new Error("文件导入目录越界");
  }
  const extensions = new Set(policy.filters.flatMap((filter) => filter.extensions));
  const staged: string[] = [];
  const created: string[] = [];
  let total = 0;
  try {
    for (const source of sourcePaths) {
      const extension = extname(source).slice(1).toLowerCase();
      if (!isAbsolute(source) || !extensions.has(extension)) throw new Error("选择的文件类型不受支持");
      const destination = join(namespace, `${randomUUID()}-${basename(source)}`);
      total += await copyBoundedFile(source, destination, Math.min(policy.maxFileBytes, maxNativeBatchBytes - total), () => created.push(destination));
      staged.push(destination);
    }
    return staged;
  } catch (error) {
    // Publish only after the whole selection succeeds. Track files only after
    // exclusive creation, so rollback never removes a pre-existing file.
    await Promise.all(created.map((path) => rm(path, { force: true })));
    throw error;
  }
}

async function copyBoundedFile(source: string, destination: string, limit: number, onCreated: () => void) {
  const before = await lstat(source);
  if (!before.isFile()) throw new Error("选择的路径不是普通文件");
  if (before.size > limit) throw new Error("选择的文件超过大小限制");
  const input = await open(source, "r");
  try {
    const opened = await input.stat();
    if (!opened.isFile() || opened.dev !== before.dev || opened.ino !== before.ino) throw new Error("选择的文件已变更");
    const output = await open(destination, "wx");
    onCreated();
    try {
      const buffer = Buffer.alloc(64 * 1024);
      let copied = 0;
      while (true) {
        // Read at most one byte over the limit, even if the source grows mid-copy.
        const { bytesRead } = await input.read(buffer, 0, Math.min(buffer.length, limit - copied + 1), null);
        if (!bytesRead) break;
        copied += bytesRead;
        if (copied > limit) throw new Error("选择的文件超过大小限制");
        await output.writeFile(buffer.subarray(0, bytesRead));
      }
      if (copied !== opened.size || (await input.stat()).size !== copied) throw new Error("选择的文件已变更");
      return copied;
    } finally { await output.close(); }
  } finally { await input.close(); }
}
