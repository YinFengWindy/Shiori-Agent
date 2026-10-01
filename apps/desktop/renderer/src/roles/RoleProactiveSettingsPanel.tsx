import { Select, cardClass, cx } from "@shiori/sdk";
import { CaretDown } from "@phosphor-icons/react";
import type React from "react";
import { useState } from "react";
import type { RoleFormState } from "../shared/types";
import { roleFieldClass, roleFieldLabelClass, rolePanelGhostButtonClass } from "./roleEditorStyles";
import { RoleEditorSection } from "./RoleEditorSection";
import { RoleProactiveExecutionFields } from "./RoleProactiveExecutionFields";
import { roleProactiveDefaults } from "./roleProactiveDefaults";
import { proactiveProfileOptions } from "./roleProactiveOptions";

type RoleProactiveSettingsPanelProps = {
  /** Offers the developer-only 开发验证 strategy. */
  devMode?: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Configures the role's proactive generation policy. */
export function RoleProactiveSettingsPanel({ devMode = false, roleForm, onUpdate }: RoleProactiveSettingsPanelProps) {
  const [executionOpen, setExecutionOpen] = useState(false);
  const profile = roleForm.proactiveProfile ?? roleProactiveDefaults.profile;

  return (
    <RoleEditorSection title="主动推送">
      <div className={cx(cardClass, "grid gap-4 p-5")} data-testid="role-proactive-config">
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
