import { useEffect, useRef, useState } from "react";
import { errorMessage, useLatestRef } from "@yinfengwindy/shiori-sdk";
import type { RoleCardExportFormat, RoleCardExportPreview } from "../../../src/bridge/roleCardExportContract";
import { previewRoleCardExport, releaseRoleCardExport } from "../roles/roleCardExportClient";
import { mascotFeedback } from "../shared/mascot/mascotFeedback";

/** Current target, immutable preview and the export operation's visible state. */
export type RoleCardExportState = {
  roleId: string;
  format: RoleCardExportFormat;
  preview: RoleCardExportPreview | null;
  status: "loading" | "ready" | "saving" | "error";
  error: string;
};

/** Coordinate previews and native saves, invalidating requests after close/target changes. */
export function useRoleCardExport() {
  const [state, setState] = useState<RoleCardExportState | null>(null);
  const currentRef = useLatestRef(state);
  const generation = useRef(0);
  function update(next: RoleCardExportState | null) { currentRef.current = next; setState(next); }
  function release(exportId: string | undefined) {
    if (exportId) void releaseRoleCardExport(exportId).catch((error: unknown) => {
      mascotFeedback.error("导出预览清理失败", { detail: errorMessage(error) });
    });
  }
  useEffect(() => () => {
    generation.current += 1;
    release(currentRef.current?.preview?.export_id);
  }, [currentRef]);

  async function open(roleId: string, format: RoleCardExportFormat = "charx") {
    if (currentRef.current?.status === "saving") return;
    const request = ++generation.current;
    release(currentRef.current?.preview?.export_id);
    update({ roleId, format, preview: null, status: "loading", error: "" });
    try {
      const preview = await previewRoleCardExport(roleId, format);
      if (request !== generation.current) { release(preview.export_id); return; }
      update({ roleId, format, preview, status: "ready", error: "" });
    } catch (error) {
      if (request === generation.current) update({ roleId, format, preview: null, status: "error", error: errorMessage(error) });
    }
  }

  function close() {
    if (currentRef.current?.status === "saving") return;
    generation.current += 1;
    release(currentRef.current?.preview?.export_id);
    update(null);
  }

  function selectFormat(format: RoleCardExportFormat) {
    if (currentRef.current && currentRef.current.format !== format) void open(currentRef.current.roleId, format);
  }

  async function save() {
    const snapshot = currentRef.current;
    if (!snapshot?.preview || snapshot.status === "saving") return;
    const request = generation.current;
    update({ ...snapshot, status: "saving", error: "" });
    try {
      const result = await window.miraDesktop.saveRoleCardExport(snapshot.preview.export_id);
      if (request !== generation.current) return;
      update({ ...snapshot, status: "ready", error: "" });
      if (result.saved) {
        mascotFeedback.success("角色已导出");
        close();
      }
    } catch (error) {
      if (request === generation.current) update({ ...snapshot, status: "ready", error: errorMessage(error) });
    }
  }

  return { state, open, close, selectFormat, save, retry: () => {
    if (currentRef.current) void open(currentRef.current.roleId, currentRef.current.format);
  } };
}
