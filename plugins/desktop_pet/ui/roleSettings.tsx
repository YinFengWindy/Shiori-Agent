import { useState } from "react";
import { Monitor } from "@phosphor-icons/react";
import {
  RoleCapabilityCard,
  roleToggleStatus,
  SettingsToggleCard,
  usePluginHostServices,
  type PluginRoleSettingsContribution,
  type PluginRoleSettingsProps,
  type PluginRpcClient,
} from "@yinfengwindy/shiori-sdk";
import { LiveCompanionSection } from "./live/LiveCompanionSection";
import { useLiveConfig, type LiveConfigAutosave } from "./live/useLiveConfig";

type PetSettingsProps = {
  roleId: string | null;
  client: PluginRpcClient;
  config: LiveConfigAutosave;
  petEnabled: boolean;
  open: boolean;
  disabled: boolean;
};

/** The body of the pet card's ⚙ dialog; a role not saved yet has nothing to configure. */
function PetSettings({ roleId, client, config, petEnabled, open, disabled }: PetSettingsProps) {
  const host = usePluginHostServices();
  if (!roleId) return <p className="m-0 text-body text-ink-muted">请先保存角色</p>;
  return <>
    <div className="flex justify-end"><host.ui.SettingsSavedStatus phase={config.savePhase} /></div>
    <LiveCompanionSection roleId={roleId} client={client} config={config} petEnabled={petEnabled} open={open} disabled={disabled} />
  </>;
}

/**
 * The pet switch edits a draft; only the role editor's Save persists it. The
 * ⚙ dialog holds 「直播陪伴」, whose settings autosave on their own; closing
 * the dialog submits the last edit at once.
 */
export function DesktopPetRoleSettings({ roleId, client, values, snapshot, disabled, onChange }: PluginRoleSettingsProps) {
  const [open, setOpen] = useState(false);
  const config = useLiveConfig(client, roleId);
  const checked = values.enabled === true;
  const unavailable = Boolean(disabled || (!snapshot?.available && !checked));
  const unavailableLabel = disabled ? "桌面服务不可用" : unavailable ? "未配置桌宠" : "";
  return (
    <RoleCapabilityCard
      icon={<Monitor className="h-5 w-5" weight="duotone" />}
      title="桌宠"
      status={roleToggleStatus(checked, unavailableLabel)}
      control={<SettingsToggleCard checked={checked} ariaLabel="桌宠" disabled={unavailable} onChange={(enabled) => onChange({ enabled })} />}
      onSettingsOpenChange={(next) => { setOpen(next); if (!next) config.commit(); }}
      settings={<PetSettings roleId={roleId} client={client} config={config} petEnabled={snapshot?.enabled === true}
        open={open} disabled={disabled === true} />}
    />
  );
}

/** Independent plugin storage participates in the host's explicit role save. */
export const desktopPetRoleSettings: PluginRoleSettingsContribution = {
  storage: "plugin",
  read: (state) => ({ enabled: state.enabled === true }),
  Component: DesktopPetRoleSettings,
  afterSave: (values, client) => client.background.call("sync", { forceVisible: values.enabled === true }),
};
