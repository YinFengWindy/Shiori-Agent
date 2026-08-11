import { ImageSquare, Monitor } from "@phosphor-icons/react";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleCapabilitySettingRow } from "../roles/RoleCapabilitySettingRow";
import { PluginHost } from "./PluginHost";

type PluginRoleCapabilityHostProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Renders loaded-plugin controls into the role capability slot. */
export function PluginRoleCapabilityHost({ activeRole, bridgeReady, roleForm, onUpdate }: PluginRoleCapabilityHostProps) {
  const desktopPetUnavailable = !bridgeReady || (!activeRole?.selected_pet_package_id && !roleForm.desktopPetEnabled);
  return <PluginHost slot="role-capability" render={({ contribution }) => {
    if (contribution.renderer === "novelai.auto-scene-cg") {
      return <RoleCapabilitySettingRow icon={ImageSquare} label={contribution.title} description="在合适的剧情节点生成场景画面。" checked={roleForm.autoSceneCgEnabled} onChange={(checked) => onUpdate((current) => ({ ...current, autoSceneCgEnabled: checked }))} />;
    }
    if (contribution.renderer === "desktop-pet.role-capability") {
      return <RoleCapabilitySettingRow icon={Monitor} label={contribution.title} description="让角色以桌面宠物形式陪伴和互动。" checked={roleForm.desktopPetEnabled} disabled={desktopPetUnavailable} disabledStatus={!bridgeReady ? "桌面服务不可用" : "未配置桌宠"} onChange={(checked) => onUpdate((current) => ({ ...current, desktopPetEnabled: checked }))} />;
    }
    return null;
  }} />;
}
