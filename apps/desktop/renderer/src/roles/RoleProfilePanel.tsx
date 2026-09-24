import { toFileUrl } from "../shared/format";
import type { RoleFormState, RoleProfileDraft, RoleRecord } from "../shared/types";
import { TiltedCard } from "../shared/ui/reactBits/TiltedCard";
import { RoleCardProfileForm } from "./RoleCardProfileForm";

type RoleProfilePanelProps = {
  activeRole: RoleRecord | null;
  previewAvatar: string | null;
  roleForm: RoleFormState;
  onOpenAssetsPage: () => void;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

// Underline-style field: opts out of the global focus halo (shadow-none) so only the bottom line responds.
const identityInputClass = "w-full border-0 border-b border-transparent bg-transparent px-0 py-1 transition hover:border-line focus:border-accent focus:shadow-none focus:outline-none";

/** Edits persisted role identity and structured runtime fields. */
export function RoleProfilePanel({
  activeRole,
  previewAvatar,
  roleForm,
  onOpenAssetsPage,
  onUpdate,
}: RoleProfilePanelProps) {
  const profile: RoleProfileDraft = roleForm.profile ?? {
    character: { behavior_rules: roleForm.systemPrompt },
  };

  function updateProfile(nextProfile: RoleProfileDraft): void {
    onUpdate((current) => ({
      ...current,
      profile: nextProfile,
      systemPrompt: nextProfile.character?.behavior_rules ?? current.systemPrompt,
    }));
  }

  return (
    <div className="grid gap-7" data-testid="role-detail-form-panel">
      <div className="grid gap-6 border-b border-line-soft pb-7 sm:grid-cols-[112px_minmax(0,1fr)]">
        <TiltedCard className="h-fit overflow-hidden rounded-xl border border-line-soft shadow-soft">
          <button
            className="group relative block h-28 w-28 overflow-hidden bg-surface-soft text-left focus:outline-none"
            data-testid="open-role-assets-button"
            data-has-preview-avatar={previewAvatar ? "true" : "false"}
            type="button"
            onClick={onOpenAssetsPage}
            aria-label="编辑角色形象"
          >
            {previewAvatar ? (
              <img className="h-full w-full object-cover transition-transform duration-panel motion-safe:group-hover:scale-105" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
            ) : (
              <span className="grid h-full w-full place-items-center text-4xl font-semibold text-ink-faint">
                {activeRole?.name.slice(0, 1).toUpperCase() || "R"}
              </span>
            )}
            <span className="absolute inset-x-0 bottom-0 bg-[rgba(15,23,42,0.62)] py-1.5 text-center text-[11px] font-medium text-white opacity-0 transition group-hover:opacity-100" aria-hidden="true">
              更换形象
            </span>
          </button>
        </TiltedCard>
        <div className="grid content-center gap-2">
          <input aria-label="角色名称" className={`${identityInputClass} text-2xl font-semibold text-ink placeholder:text-ink-faint`} data-testid="edit-role-name" value={roleForm.name} placeholder="未命名角色" onChange={(event) => onUpdate((current) => ({ ...current, name: event.target.value }))} />
          <input aria-label="角色简介" className={`${identityInputClass} text-sm leading-6 text-ink-muted placeholder:text-ink-faint`} data-testid="edit-role-description" value={roleForm.description} placeholder="添加一行角色简介" onChange={(event) => onUpdate((current) => ({ ...current, description: event.target.value }))} />
        </div>
      </div>
      <RoleCardProfileForm profile={profile} onUpdate={updateProfile} />
    </div>
  );
}
