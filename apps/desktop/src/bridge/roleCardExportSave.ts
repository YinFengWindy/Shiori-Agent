import { randomUUID } from "node:crypto";
import { writeFile, rename, rm, copyFile } from "node:fs/promises";
import { constants } from "node:fs";
import { basename, dirname, join } from "node:path";
import type { SaveDialogOptions, SaveDialogReturnValue } from "electron";
import type { DesktopBridgeClient } from "./bridgeClient.js";
import type { RoleCardExportSaveResult } from "./roleCardExportContract.js";

/** Save only a backend-owned role-card snapshot to a user-selected destination. */
export async function saveRoleCardExport(
  exportId: unknown,
  bridge: Pick<DesktopBridgeClient, "invoke">,
  showSaveDialog: (options: SaveDialogOptions) => Promise<SaveDialogReturnValue>,
): Promise<RoleCardExportSaveResult> {
  if (typeof exportId !== "string" || !/^[a-f0-9]{32}$/.test(exportId)) {
    throw new Error("导出预览无效，请重新预览");
  }
  const response = await bridge.invoke({ method: "roles.cardExport.read", payload: { export_id: exportId } });
  if (response.error) throw new Error(response.error.message);
  const { name, format, data_base64: encoded } = response.payload;
  if (typeof name !== "string" || (format !== "charx" && format !== "png" && format !== "json")
    || typeof encoded !== "string" || !encoded || encoded.length > 70 * 1024 * 1024) {
    throw new Error("角色卡导出数据无效，请重新预览");
  }
  const data = Buffer.from(encoded, "base64");
  const result = await showSaveDialog({
    title: "导出角色",
    defaultPath: `${safeRoleFilename(name)}.${format}`,
    filters: [{ name: `${format.toUpperCase()} 角色卡`, extensions: [format] }],
  });
  if (result.canceled || !result.filePath) return { saved: false };
  const destination = result.filePath.toLowerCase().endsWith(`.${format}`) ? result.filePath : `${result.filePath}.${format}`;
  // Atomic replacement keeps a previous export intact if writing fails midway.
  const temporary = join(dirname(destination), `.${basename(destination)}.${randomUUID()}.tmp`);
  try {
    await writeFile(temporary, data, { flag: "wx" });
    if (destination === result.filePath) {
      await rename(temporary, destination);
    } else {
      // The picker did not confirm overwriting the extension-adjusted path.
      // Exclusive copying works on removable filesystems without hard-link support.
      await copyFile(temporary, destination, constants.COPYFILE_EXCL);
    }
  } finally {
    await rm(temporary, { force: true });
  }
  return { saved: true };
}

function safeRoleFilename(name: string) {
  const clean = Array.from(name).filter((character) => character.charCodeAt(0) >= 32)
    .join("").replace(/[<>:"/\\|?*]/g, "_").slice(0, 100).replace(/[. ]+$/, "").trim();
  return !clean || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(clean) ? `角色-${clean || "未命名"}` : clean;
}
