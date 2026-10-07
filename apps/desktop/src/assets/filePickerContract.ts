import { extname, isAbsolute } from "node:path";
import type { NativeFilePathPickerOptions, NativeFilePickerOptions } from "@yinfengwindy/shiori-sdk/contract";

/** Hard host ceilings; a plugin may request a smaller per-file limit. */
export const maxNativeFileBytes = 16 * 1024 ** 3;
export const maxNativeBatchBytes = 32 * 1024 ** 3;
export const maxNativeFileCount = 16;

const selectionPolicyKeys = ["filters", "multiple", "maxFileBytes"];

/** Rejects path-bearing or unbounded IPC options before opening a staging dialog. */
export function normalizeFilePickerOptions(value: unknown): NativeFilePickerOptions {
  const policy = normalizeSelectionPolicy(value, [...selectionPolicyKeys, "namespace"]);
  const { namespace } = value as Record<string, unknown>;
  if (typeof namespace !== "string" || !/^[a-z][a-z0-9_-]{0,63}$/.test(namespace)) {
    throw new Error("文件导入命名空间无效");
  }
  return { namespace, ...policy };
}

/** Rejects path-bearing or unbounded IPC options before opening an original-path dialog. */
export function normalizeFilePathPickerOptions(value: unknown): NativeFilePathPickerOptions {
  return normalizeSelectionPolicy(value, selectionPolicyKeys);
}

/**
 * Checks the dialog's paths against the policy's count and extension limits
 * before any of them is read, so copying and original-path picks admit the
 * same selections.
 */
export function assertPickedSelection(sourcePaths: readonly string[], policy: NativeFilePathPickerOptions) {
  if (sourcePaths.length > (policy.multiple ? maxNativeFileCount : 1)) throw new Error("选择的文件数量超过限制");
  const extensions = new Set(policy.filters.flatMap((filter) => filter.extensions));
  for (const source of sourcePaths) {
    if (!isAbsolute(source) || !extensions.has(extname(source).slice(1).toLowerCase())) {
      throw new Error("选择的文件类型不受支持");
    }
  }
}

function normalizeSelectionPolicy(value: unknown, allowedKeys: readonly string[]): NativeFilePathPickerOptions {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("文件选择参数无效");
  const allowed = new Set(allowedKeys);
  if (Object.keys(value).some((key) => !allowed.has(key))) throw new Error("文件选择参数包含不支持的字段");
  const { filters, multiple, maxFileBytes } = value as Record<string, unknown>;
  if (multiple !== undefined && typeof multiple !== "boolean") throw new Error("文件多选参数无效");
  if (typeof maxFileBytes !== "number" || !Number.isSafeInteger(maxFileBytes) || maxFileBytes < 1 || maxFileBytes > maxNativeFileBytes) {
    throw new Error("文件大小限制无效");
  }
  if (!Array.isArray(filters) || filters.length < 1 || filters.length > 8) throw new Error("文件过滤条件无效");
  const normalizedFilters = filters.map((filter: unknown) => {
    if (!filter || typeof filter !== "object" || Array.isArray(filter)) throw new Error("文件过滤条件无效");
    const { name, extensions } = filter as Record<string, unknown>;
    if (typeof name !== "string" || !name.trim() || name.length > 80
      || !Array.isArray(extensions) || extensions.length < 1 || extensions.length > 16
      || extensions.some((extension) => typeof extension !== "string" || !/^[a-z0-9]{1,16}$/i.test(extension))) {
      throw new Error("文件过滤条件无效");
    }
    return { name: name.trim(), extensions: extensions.map((extension: string) => extension.toLowerCase()) };
  });
  return { filters: normalizedFilters, multiple: multiple === true, maxFileBytes };
}
