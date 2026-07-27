import { useLayoutEffect, useRef } from "react";
import { toFileUrl } from "../shared/format";
import { cx, inputClass } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { TiltedCard } from "../shared/ui/reactBits/TiltedCard";

type RoleProfilePanelProps = {
  activeRole: RoleRecord | null;
  previewAvatar: string | null;
  roleForm: RoleFormState;
  onOpenAssetsPage: () => void;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Edits the role identity and system prompt. */
export function RoleProfilePanel({
  activeRole,
  previewAvatar,
  roleForm,
  onOpenAssetsPage,
  onUpdate,
}: RoleProfilePanelProps) {
  const promptRef = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const textarea = promptRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.max(textarea.scrollHeight, 240)}px`;
  }, [roleForm.systemPrompt]);

  return (
    <div className="grid gap-6 lg:grid-cols-[160px_minmax(0,1fr)]" data-testid="role-detail-form-panel">
      <div className="grid content-start gap-3">
        <TiltedCard className="overflow-hidden rounded-[22px] border border-white/45 shadow-[0_18px_42px_rgba(29,17,12,0.3)]">
          <button
            className="group relative block h-40 w-40 overflow-hidden bg-[rgba(37,24,18,0.3)] text-left focus:outline-none"
            data-testid="open-role-assets-button"
            data-has-preview-avatar={previewAvatar ? "true" : "false"}
            type="button"
            onClick={onOpenAssetsPage}
          >
            {previewAvatar ? (
              <img className="h-full w-full object-cover transition duration-500 group-hover:scale-105" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
            ) : (
              <div className="grid h-full w-full place-items-center bg-[radial-gradient(circle_at_top_left,#f9c3a4_0%,#9f4c2e_48%,#44271f_100%)] text-5xl font-semibold text-white">
                {activeRole?.name.slice(0, 1).toUpperCase() || "R"}
              </div>
            )}
            <span className="absolute inset-x-0 bottom-0 bg-black/45 px-3 py-2 text-xs text-white opacity-0 transition group-hover:opacity-100">管理素材</span>
          </button>
        </TiltedCard>
      </div>
      <div className="grid gap-5">
        <label className="grid gap-1.5 text-xs text-white/90">
          <span>名称</span>
          <input className={cx(inputClass, "border-white/35 bg-white/82 text-[#241914] placeholder:text-[#8d817b]")} data-testid="edit-role-name" value={roleForm.name} placeholder="输入角色名称" onChange={(event) => onUpdate((current) => ({ ...current, name: event.target.value }))} />
        </label>
        <label className="grid gap-1.5 text-xs text-white/90">
          <span>简介</span>
          <input className={cx(inputClass, "border-white/35 bg-white/82 text-[#241914] placeholder:text-[#8d817b]")} data-testid="edit-role-description" value={roleForm.description} placeholder="简短描述这个角色" onChange={(event) => onUpdate((current) => ({ ...current, description: event.target.value }))} />
        </label>
        <label className="grid gap-2 text-xs text-white/90">
          <span>系统提示词</span>
          <textarea ref={promptRef} className={cx(inputClass, "min-h-[240px] resize-y border-white/35 bg-white/82 text-[#241914] placeholder:text-[#8d817b]")} data-testid="edit-role-prompt" value={roleForm.systemPrompt} placeholder="定义这个角色的行为、语气和边界" onChange={(event) => onUpdate((current) => ({ ...current, systemPrompt: event.target.value }))} />
        </label>
      </div>
    </div>
  );
}
