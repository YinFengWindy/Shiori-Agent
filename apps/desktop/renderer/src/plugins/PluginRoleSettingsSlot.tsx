import { PluginHostServicesProvider, type PluginRoleSettingsContribution, type PluginRoleValues } from "@yinfengwindy/shiori-sdk";
import { pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { pluginHostServicesFor } from "./pluginHostServices";
import type { PluginRoleSettingsDraft } from "./pluginRoleSettings";
import { usePluginEnabledState } from "./usePluginEnabledState";
import { usePluginRpcClient } from "./usePluginRpcClient";

type SlotProps = {
  roleId: string | null;
  /** The edited role's draft mood catalog, handed to every card. */
  moodCatalog: readonly string[];
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
export function PluginRoleSettingsSlot({ roleId, moodCatalog, drafts, snapshots, disabled, onChange }: SlotProps) {
  const enabled = usePluginEnabledState();
  return pluginRoleSettingsRegistry.list().filter((entry) => enabled(entry.pluginId)).map((entry) => (
    <PluginRoleSettingsEntry key={`${entry.pluginId}:${roleId ?? "new"}`} entry={entry} roleId={roleId} moodCatalog={moodCatalog}
      values={drafts[entry.pluginId] ?? entry.read({})} snapshot={snapshots?.[entry.pluginId]} disabled={disabled}
      onChange={(values) => onChange({ ...drafts, [entry.pluginId]: values })} />
  ));
}

/** One contribution with its scoped client and host services. */
function PluginRoleSettingsEntry({ entry, roleId, moodCatalog, values, snapshot, disabled, onChange }: {
  entry: PluginRoleSettingsContribution & { pluginId: string };
  roleId: string | null;
  moodCatalog: readonly string[];
  values: PluginRoleValues;
  snapshot?: PluginRoleValues;
  disabled?: boolean;
  onChange: (values: PluginRoleValues) => void;
}) {
  const client = usePluginRpcClient(entry.pluginId);
  return <PluginHostServicesProvider services={pluginHostServicesFor(entry.pluginId)}>
    <entry.Component roleId={roleId} client={client} moodCatalog={moodCatalog} values={values} snapshot={snapshot} disabled={disabled} onChange={onChange} />
  </PluginHostServicesProvider>;
}
