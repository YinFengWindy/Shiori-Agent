import { PluginHostServicesProvider, type PluginRoleSettingsContribution, type PluginRoleValues } from "@yinfengwindy/shiori-sdk";
import { pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { pluginHostServicesFor } from "./pluginHostServices";
import type { PluginRoleSettingsDraft } from "./pluginRoleSettings";
import { usePluginEnabledState } from "./usePluginEnabledState";
import { usePluginRpcClient } from "./usePluginRpcClient";

type SlotProps = {
  roleId: string | null;
  drafts: PluginRoleSettingsDraft;
  snapshots?: PluginRoleSettingsDraft;
  disabled?: boolean;
  onChange: (drafts: PluginRoleSettingsDraft) => void;
};

/**
 * Mounts active plugins' role settings while preserving all stored drafts.
 * Each card is keyed by role, so plugin-private state in its settings dialog
 * never outlives the role it was opened for.
 */
export function PluginRoleSettingsSlot({ roleId, drafts, snapshots, disabled, onChange }: SlotProps) {
  const enabled = usePluginEnabledState();
  return pluginRoleSettingsRegistry.list().filter((entry) => enabled(entry.pluginId)).map((entry) => (
    <PluginRoleSettingsEntry key={`${entry.pluginId}:${roleId ?? "new"}`} entry={entry} roleId={roleId}
      values={drafts[entry.pluginId] ?? entry.read({})} snapshot={snapshots?.[entry.pluginId]} disabled={disabled}
      onChange={(values) => onChange({ ...drafts, [entry.pluginId]: values })} />
  ));
}

/** One contribution with its scoped client and host services, like the role UI slot. */
function PluginRoleSettingsEntry({ entry, roleId, values, snapshot, disabled, onChange }: {
  entry: PluginRoleSettingsContribution & { pluginId: string };
  roleId: string | null;
  values: PluginRoleValues;
  snapshot?: PluginRoleValues;
  disabled?: boolean;
  onChange: (values: PluginRoleValues) => void;
}) {
  const client = usePluginRpcClient(entry.pluginId);
  return <PluginHostServicesProvider services={pluginHostServicesFor(entry.pluginId)}>
    <entry.Component roleId={roleId} client={client} values={values} snapshot={snapshot} disabled={disabled} onChange={onChange} />
  </PluginHostServicesProvider>;
}
