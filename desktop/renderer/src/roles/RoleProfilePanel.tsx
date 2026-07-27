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
    <div className="grid gap-7" data-testid="role-detail-form-panel">
      <div className="grid gap-5 border-b border-[#eaded6] pb-7 sm:grid-cols-[104px_minmax(0,1fr)]">
        <TiltedCard className="h-fit overflow-hidden rounded-md border border-[#e3d2c8] shadow-[0_10px_24px_rgba(76,42,28,0.14)]">
          <button
            className="group relative block h-[104px] w-[104px] overflow-hidden bg-[rgba(37,24,18,0.3)] text-left focus:outline-none"
            data-testid="open-role-assets-button"
            data-has-preview-avatar={previewAvatar ? "true" : "false"}
            type="button"
            onClick={onOpenAssetsPage}
          >
            {previewAvatar ? (
              <img className="h-full w-full object-cover transition duration-500 group-hover:scale-105" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
            ) : (
              <div className="grid h-full w-full place-items-center bg-[radial-gradient(circle_at_top_left,#f9c3a4_0%,#9f4c2e_48%,#44271f_100%)] text-4xl font-semibold text-white">
                {activeRole?.name.slice(0, 1).toUpperCase() || "R"}
              </div>
            )}
            <span className="absolute inset-x-0 bottom-0 bg-black/45 px-3 py-2 text-xs text-white opacity-0 transition group-hover:opacity-100">管理素材</span>
          </button>
        </TiltedCard>
        <div className="grid content-start gap-4">
          <div className="grid gap-1"><h1 className="text-xl font-semibold text-[#322019]">{roleForm.name || "未命名角色"}</h1><button className="w-fit text-xs text-[#9b5b3b] transition hover:text-[#69371f]" type="button" onClick={onOpenAssetsPage}>管理头像与素材</button></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-xs font-medium text-[#66544b]"><span>名称</span><input className={cx(inputClass, "h-10 border-[#d9c8bf] !bg-white px-3 py-2 text-[#2d1d17] placeholder:text-[#a18e84] focus:border-[#a85d38] focus:ring-2 focus:ring-[#a85d38]/15")} data-testid="edit-role-name" value={roleForm.name} placeholder="输入角色名称" onChange={(event) => onUpdate((current) => ({ ...current, name: event.target.value }))} /></label>
            <label className="grid gap-1.5 text-xs font-medium text-[#66544b]"><span>简介</span><input className={cx(inputClass, "h-10 border-[#d9c8bf] !bg-white px-3 py-2 text-[#2d1d17] placeholder:text-[#a18e84] focus:border-[#a85d38] focus:ring-2 focus:ring-[#a85d38]/15")} data-testid="edit-role-description" value={roleForm.description} placeholder="简短描述这个角色" onChange={(event) => onUpdate((current) => ({ ...current, description: event.target.value }))} /></label>
          </div>
        </div>
      </div>
      <label className="grid gap-2 text-sm text-[#3d2920]">
        <span className="font-medium">系统提示词</span>
        <textarea ref={promptRef} className={cx(inputClass, "min-h-[320px] resize-y border-[#d9c8bf] !bg-[#fffdfa] px-4 py-3 font-mono text-[13px] leading-6 text-[#2d1d17] placeholder:text-[#a18e84] focus:border-[#a85d38] focus:ring-2 focus:ring-[#a85d38]/15")} data-testid="edit-role-prompt" value={roleForm.systemPrompt} placeholder="定义这个角色的行为、语气和边界" onChange={(event) => onUpdate((current) => ({ ...current, systemPrompt: event.target.value }))} />
      </label>
    </div>
  );
}
