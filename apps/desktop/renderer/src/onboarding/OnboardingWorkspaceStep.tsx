import { ArrowRight, User } from "@phosphor-icons/react";
import { Select } from "../shared/ui/Select";
import { inputClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import { OnboardingCard } from "./OnboardingCard";
import { onboardingActionClass } from "./onboardingStyles";

/** Presents the role to start with and enters its real workspace before completion. */
export function OnboardingWorkspaceStep({ roles, role, entering, onSelect, onEnter }: {
  roles: RoleRecord[];
  role: RoleRecord;
  entering: boolean;
  onSelect: (roleId: string) => void;
  onEnter: (role: RoleRecord) => Promise<void>;
}) {
  return (
    <OnboardingCard footer={(
      <button type="button" className={onboardingActionClass} disabled={entering} onClick={() => void onEnter(role)}>
        {entering ? "正在进入" : "进入 Shiori"}<ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
      </button>
    )}>
      <div className="flex items-center gap-5 pb-5">
        <div className="grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-full border-4 border-white/90 bg-gradient-accent-soft text-accent-text shadow-panel">
          {role.avatar_abs ? <img className="h-full w-full object-cover" src={window.miraDesktop.localAssetUrl(role.avatar_abs)} alt={role.name} /> : <User className="h-8 w-8" aria-hidden="true" />}
        </div>
        <div className="grid min-w-0 flex-1 gap-2">
          <h2 className="m-0 break-words font-display text-headline text-ink">{role.name}</h2>
          {role.description ? <p className="m-0 break-words text-body text-ink-secondary">{role.description}</p> : null}
          {roles.length > 1 ? <Select aria-label="选择角色" value={role.id} onValueChange={onSelect} disabled={entering} className={inputClass}
            options={roles.map((item) => ({ value: item.id, label: item.name }))} /> : null}
        </div>
      </div>
    </OnboardingCard>
  );
}
