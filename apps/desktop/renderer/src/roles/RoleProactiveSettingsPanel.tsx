import { Select } from "../shared/ui/Select";
import { CaretDown } from "@phosphor-icons/react";
import type React from "react";
import { useState } from "react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { cardClass, cx } from "../shared/styles";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { RoleCapabilityBadge } from "./RoleCapabilityCard";
import { roleToggleStatus } from "./roleCapabilityStatus";
import { buildProactiveTransportSequence } from "./roleChannelBindings";
import { roleChannelLabel, type RoleChannelCatalog } from "./roleChannelCatalog";
import { roleFieldClass, roleFieldLabelClass, rolePanelGhostButtonClass } from "./roleEditorStyles";
import { RoleEditorSection } from "./RoleEditorSection";
import { RoleProactiveExecutionFields } from "./RoleProactiveExecutionFields";
import { roleProactiveDefaults } from "./roleProactiveDefaults";
import { proactiveProfileOptions } from "./roleProactiveOptions";

type RoleProactiveSettingsPanelProps = {
  bindings: RoleChannelBinding[];
  /** Supplies channel display labels; null while `channels.list` loads. */
  channels: RoleChannelCatalog;
  /** Offers the developer-only 开发验证 strategy. */
  devMode?: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Configures the delivery policy after role channels have been selected. */
export function RoleProactiveSettingsPanel({ bindings, channels, devMode = false, roleForm, onUpdate }: RoleProactiveSettingsPanelProps) {
  const [executionOpen, setExecutionOpen] = useState(false);
  const enabled = Boolean(roleForm.proactiveEnabled ?? roleProactiveDefaults.enabled);
  const profile = roleForm.proactiveProfile ?? roleProactiveDefaults.profile;
  const targetChannel = roleForm.proactiveTargetChannel ?? roleProactiveDefaults.targetChannel;
  const targetChatId = roleForm.proactiveTargetChatId ?? roleProactiveDefaults.targetChatId;
  const selectedBinding = bindings.find((binding) => binding.channel === targetChannel && binding.chat_id === targetChatId);
  const transportSequence = selectedBinding ? buildProactiveTransportSequence(bindings, targetChannel, targetChatId) : [];
  const usableBindings = bindings.filter((binding) => binding.chat_id.trim());
  const bindingLabel = (binding: RoleChannelBinding) => `${roleChannelLabel(binding.channel, channels)} · ${binding.chat_id}`;

  return (
    <RoleEditorSection
      title="主动推送"
      action={(
        <div className="flex items-center gap-3">
          <RoleCapabilityBadge status={roleToggleStatus(enabled)} />
          <SettingsToggleCard checked={enabled} ariaLabel="主动推送" onChange={(checked) => onUpdate((current) => ({ ...current, proactiveEnabled: checked }))} />
        </div>
      )}
    >
      <div className={cx(cardClass, "grid gap-4 p-5")} data-testid="role-proactive-config">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className={roleFieldLabelClass}>
            <span>首选投递位置</span>
            <Select
              aria-label="首选投递位置"
              className={roleFieldClass}
              value={`${targetChannel}:${targetChatId}`}
              onValueChange={(value) => {
                const selected = bindings.find((binding) => `${binding.channel}:${binding.chat_id}` === value);
                onUpdate((current) => ({ ...current, proactiveTargetChannel: selected?.channel ?? roleProactiveDefaults.targetChannel, proactiveTargetChatId: selected?.chat_id ?? roleProactiveDefaults.targetChatId }));
              }}
              options={[{ value: ":", label: "未选择" }, ...usableBindings.map((binding) => ({ value: `${binding.channel}:${binding.chat_id}`, label: bindingLabel(binding) }))]}
            />
          </label>
          <label className={roleFieldLabelClass}>
            <span>推送策略</span>
            <Select aria-label="推送策略" className={roleFieldClass} value={profile} onValueChange={(value) => onUpdate((current) => ({ ...current, proactiveProfile: value }))} options={proactiveProfileOptions(devMode, profile)} />
          </label>
        </div>
        {transportSequence.length ? (
          <ol className="m-0 grid list-none gap-1 p-0" data-testid="role-proactive-sequence">
            {transportSequence.map((binding, index) => (
              <li className="flex min-w-0 items-center gap-3 border-b border-line-soft py-2 last:border-b-0" key={`${binding.channel}:${binding.chat_id}`}>
                <span className={cx("grid h-6 w-6 shrink-0 place-items-center rounded-md text-caption", index === 0 ? "bg-success-soft font-medium text-success-text" : "bg-surface-soft text-ink-muted")}>{index + 1}</span>
                <span className="min-w-0 truncate text-body text-ink-secondary">{bindingLabel(binding)}</span>
                <span className="ml-auto shrink-0 text-caption text-ink-muted">{index === 0 ? "首选" : "无回复后尝试"}</span>
              </li>
            ))}
          </ol>
        ) : null}
        <div className="grid gap-4">
          <button className={cx(rolePanelGhostButtonClass, "w-fit")} type="button" aria-expanded={executionOpen} onClick={() => setExecutionOpen((current) => !current)}>
            执行参数
            <CaretDown className={cx("h-3.5 w-3.5 transition-transform duration-quick", executionOpen && "rotate-180")} weight="bold" aria-hidden="true" />
          </button>
          {executionOpen ? <RoleProactiveExecutionFields roleForm={roleForm} onUpdate={onUpdate} /> : null}
        </div>
      </div>
    </RoleEditorSection>
  );
}
