import { BridgeError } from "@yinfengwindy/shiori-sdk";
import type { RoleCardExportFormat, RoleCardExportPreview } from "../../../src/bridge/roleCardExportContract";

/** Ask the role owner for a frozen, format-specific preview. */
export async function previewRoleCardExport(roleId: string, format: RoleCardExportFormat) {
  const payload = await request("preview", { role_id: roleId, format });
  const character = object(payload.character);
  if (typeof payload.export_id !== "string" || typeof payload.name !== "string"
    || typeof payload.description !== "string" || payload.format !== format
    || typeof payload.size !== "number" || !Array.isArray(payload.assets)) {
    throw new Error("角色卡预览数据无效");
  }
  const preview: RoleCardExportPreview = {
    export_id: payload.export_id, name: payload.name, description: payload.description, format, size: payload.size,
    character: {
      profile: string(character.profile), personality: string(character.personality),
      behavior_rules: string(character.behavior_rules), response_constraints: string(character.response_constraints),
      nickname: string(character.nickname),
    },
    assets: payload.assets.map((value) => {
      const asset = object(value);
      if (!Array.isArray(asset.labels) || typeof asset.preview_url !== "string"
        || !asset.preview_url.startsWith("data:image/png;base64,")) throw new Error("角色图片预览无效");
      return { preview_url: asset.preview_url, labels: asset.labels.map(string) };
    }),
  };
  return preview;
}

/** Release a superseded snapshot; no source-role data is changed. */
export async function releaseRoleCardExport(exportId: string) {
  await request("release", { export_id: exportId });
}

async function request(operation: string, payload: Record<string, unknown>) {
  const response = await window.miraDesktop.invoke({ method: `roles.cardExport.${operation}`, payload });
  if (response.error) throw new BridgeError(response.error.message, response.error.code, response.error.details);
  return response.payload;
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("角色卡预览数据无效");
  return value as Record<string, unknown>;
}

function string(value: unknown) {
  if (typeof value !== "string") throw new Error("角色资料预览无效");
  return value;
}
