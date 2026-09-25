import { Select } from "../shared/ui/Select";
import { CaretDown } from "@phosphor-icons/react";
import type React from "react";
import { useState } from "react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { badgeClass, cardClass, cx } from "../shared/styles";
import type { RoleChannelBinding, RoleFormState, RoleProactiveCandidate } from "../shared/types";
import { RoleCapabilityBadge } from "./RoleCapabilityCard";
import { roleToggleStatus } from "./roleCapabilityStatus";
import type { RoleChannelCatalog } from "./roleChannelCatalog";
import { roleBindingDisplayLabel } from "./roleChatTypes";
import { roleFieldClass, roleFieldLabelClass, rolePanelGhostButtonClass } from "./roleEditorStyles";
import { RoleEditorSection } from "./RoleEditorSection";
import { isRoleProactiveCandidate, selectableProactiveBindings, setRoleProactiveCandidate } from "./roleProactiveCandidates";
import { RoleProactiveExecutionFields } from "./RoleProactiveExecutionFields";
import { roleProactiveDefaults } from "./roleProactiveDefaults";
import { proactiveProfileOptions } from "./roleProactiveOptions";

type RoleProactiveSettingsPanelProps = {
  bindings: RoleChannelBinding[];
  /** Supplies channel display labels; null while `channels.list` loads. */
  channels: RoleChannelCatalog;
  /** The candidate the next proactive message would go to, as selected by the backend; null when unknown. */
  currentTarget: RoleProactiveCandidate | null;
  /** Offers the developer-only 开发验证 strategy. */
  devMode?: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Configures which bound sessions receive proactive messages, and the delivery policy. */
export function RoleProactiveSettingsPanel({ bindings, channels, currentTarget, devMode = false, roleForm, onUpdate }: RoleProactiveSettingsPanelProps) {
  const [executionOpen, setExecutionOpen] = useState(false);
  const enabled = Boolean(roleForm.proactiveEnabled ?? roleProactiveDefaults.enabled);
  const profile = roleForm.proactiveProfile ?? roleProactiveDefaults.profile;
  const candidates = roleForm.proactiveCandidates ?? [];

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
        <fieldset className="m-0 grid min-w-0 border-0 p-0" data-testid="role-proactive-candidates">
          <legend className={cx(roleFieldLabelClass, "mb-1 p-0")}>接收会话</legend>
          {selectableProactiveBindings(bindings).map((binding) => {
            // Only the backend decides which candidate is current; the panel just marks it.
            const current = currentTarget?.channel === binding.channel && currentTarget.chat_id === binding.chat_id;
            return (
              <label className="flex min-w-0 items-center gap-3 border-b border-line-soft py-2 last:border-b-0" key={`${binding.channel}:${binding.chat_id}`}>
                <input
                  type="checkbox"
                  className="h-4 w-4 shrink-0 accent-accent"
                  checked={isRoleProactiveCandidate(binding, candidates)}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    onUpdate((form) => ({ ...form, proactiveCandidates: setRoleProactiveCandidate(form.channelBindings ?? [], form.proactiveCandidates ?? [], binding, checked) }));
                  }}
                />
                <span className="min-w-0 truncate text-body text-ink-secondary">{roleBindingDisplayLabel(binding, channels)}</span>
                {current ? <span className={cx(badgeClass, "ml-auto shrink-0")} data-testid="role-proactive-current">当前</span> : null}
              </label>
            );
          })}
        </fieldset>
        <label className={cx(roleFieldLabelClass, "sm:max-w-[50%]")}>
          <span>推送策略</span>
          <Select aria-label="推送策略" className={roleFieldClass} value={profile} onValueChange={(value) => onUpdate((current) => ({ ...current, proactiveProfile: value }))} options={proactiveProfileOptions(devMode, profile)} />
        </label>
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
