import type { NativeFilePickerOptions } from "@shiori/plugin-sdk/contract";

/** Hard host ceilings; a plugin may request a smaller per-file limit. */
export const maxNativeFileBytes = 32 * 1024 * 1024;
export const maxNativeBatchBytes = 64 * 1024 * 1024;
export const maxNativeFileCount = 16;

/** Rejects path-bearing or unbounded IPC options before opening a native dialog. */
export function normalizeFilePickerOptions(value: unknown): NativeFilePickerOptions {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("文件选择参数无效");
  const allowed = new Set(["namespace", "filters", "multiple", "maxFileBytes"]);
  if (Object.keys(value).some((key) => !allowed.has(key))) throw new Error("文件选择参数包含不支持的字段");
  const { namespace, filters, multiple, maxFileBytes } = value as Record<string, unknown>;
  if (typeof namespace !== "string" || !/^[a-z][a-z0-9_-]{0,63}$/.test(namespace)) {
    throw new Error("文件导入命名空间无效");
  }
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
  return { namespace, filters: normalizedFilters, multiple: multiple === true, maxFileBytes };
}
