import { useId, useState, type ReactNode } from "react";
import { SettingsDisclosure, SettingsDisclosureToggle } from "../settings/SettingsDisclosure";
import { SettingsSectionCard } from "../settings/SettingsFieldPrimitives";
import { SettingsSaveFeedback } from "../settings/SettingsSaveFeedback";
import { SettingsSavedIndicator } from "../settings/SettingsSavedIndicator";
import { SettingsStatus } from "../settings/SettingsStatusSlot";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";
import { InlineError } from "../shared/feedback/InlineError";
import { describePluginConfigFields, partitionPluginConfigFields, type PluginConfigField } from "./jsonSchemaForm";
import { PluginConfigFieldRow } from "./PluginConfigFieldRow";
import { usePluginConfigController } from "./usePluginConfigController";

/** The raw-JSON fields, folded under 「高级」 so the everyday form stays plain. */
function AdvancedFields({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <section className="grid gap-2.5">
      <SettingsDisclosureToggle open={open} controls={bodyId} onToggle={() => setOpen((current) => !current)}>高级</SettingsDisclosureToggle>
      <SettingsDisclosure open={open} id={bodyId}>
        <SettingsSectionCard>{children}</SettingsSectionCard>
      </SettingsDisclosure>
    </section>
  );
}

type PluginSchemaSettingsSectionProps = { pluginId: string };

/** Renders and autosaves a plugin's config form, generated from its declared JSON Schema. */
export function PluginSchemaSettingsSection({ pluginId }: PluginSchemaSettingsSectionProps) {
  const { schema, envStatus, draft, loadError, savePhase, statusMessage, updateDraft, retrySave, reloadConfig } =
    usePluginConfigController(pluginId);

  if (loadError) {
    return (
      <InlineError
        persona="pluginConfigLoadFailed"
        message={`插件配置加载失败：${loadError}`}
        actions={<button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={reloadConfig}>重新加载</button>}
      />
    );
  }
  if (!schema || !draft || !envStatus) {
    return <div className="text-sm text-ink-muted">正在加载插件配置…</div>;
  }

  const { primary, advanced } = partitionPluginConfigFields(describePluginConfigFields(schema));
  const row = (field: PluginConfigField) => (
    <PluginConfigFieldRow
      key={field.key}
      field={field}
      value={draft[field.key]}
      envResolved={envStatus[field.key] === "set"}
      onChange={(value) => updateDraft((current) => ({ ...current, [field.key]: value }))}
    />
  );
  return (
    <div className="grid gap-7">
      <SettingsStatus><SettingsSavedIndicator phase={savePhase} /></SettingsStatus>
      <SettingsSaveFeedback
        phase={savePhase}
        message={statusMessage}
        onRetry={retrySave}
        onReload={reloadConfig}
      />
      {primary.length > 0 ? <SettingsSectionCard>{primary.map(row)}</SettingsSectionCard> : null}
      {advanced.length > 0 ? <AdvancedFields>{advanced.map(row)}</AdvancedFields> : null}
    </div>
  );
}
