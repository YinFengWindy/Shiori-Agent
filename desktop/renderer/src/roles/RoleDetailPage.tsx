import { toFileUrl } from "../shared/format";
import { useLayoutEffect, useRef } from "react";
import { ArrowDownIcon, ArrowUpIcon, DeleteIcon, ResetIcon, SaveIcon } from "../shared/icons";
import { cx, focusResetClass, inputClass } from "../shared/styles";
import type { RoleChannelBinding, RoleFormState, RoleRecord } from "../shared/types";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import {
  changeRoleBindingChannel,
  createRoleChannelBinding,
  buildProactiveTransportSequence,
  isDesktopRoleBinding,
  moveRoleChannelBinding,
  roleBindingAllowFromLabel,
  roleBindingChannelLabel,
} from "./roleChannelBindings";
import { captureRoleDetailScrollTop, restoreRoleDetailScrollTop } from "./roleDetailScrollState";

type RoleDetailPageProps = {
  activeIllustration: string;
  activeRole: RoleRecord | null;
  activeRoleId: string;
  bridgeReady: boolean;
  previewAvatar: string | null;
  chatBackgroundUrl: string;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onBackToList: () => void;
  onOpenAssetsPage: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
};

/** Renders the second-level role detail page and hosts the role editor form. */
export function RoleDetailPage({
  activeRole,
  activeRoleId,
  bridgeReady,
  previewAvatar,
  chatBackgroundUrl,
  roleForm,
  roleFormDirty,
  savingRole,
  onBackToList,
  onOpenAssetsPage,
  onUpdateRoleForm,
  onResetRoleForm,
  onSaveRole,
}: RoleDetailPageProps) {
  const pageRef = useRef<HTMLElement | null>(null);
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const pendingScrollTopRef = useRef<number | null>(null);
  const backIcon = (
    <svg viewBox="0 0 1024 1024" className="h-5 w-5 fill-[#111111]" aria-hidden="true">
      <path d="M631.04 161.941333a42.666667 42.666667 0 0 1 63.061333 57.386667l-2.474666 2.730667-289.962667 292.245333 289.706667 287.402667a42.666667 42.666667 0 0 1 2.730666 57.6l-2.474666 2.752a42.666667 42.666667 0 0 1-57.6 2.709333l-2.752-2.474667-320-317.44a42.666667 42.666667 0 0 1-2.709334-57.6l2.474667-2.752 320-322.56z" />
    </svg>
  );
  const floatingActionClass =
    "grid h-10 w-10 place-items-center rounded-full border bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 disabled:translate-y-0 disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-[#b8b8b8] disabled:shadow-none";

  useLayoutEffect(() => {
    const textarea = promptRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [roleForm.systemPrompt]);

  useLayoutEffect(() => {
    pendingScrollTopRef.current = restoreRoleDetailScrollTop(pageRef.current, pendingScrollTopRef.current);
  }, [roleForm]);

  function preserveScrollDuringFormUpdate(
    next: React.SetStateAction<RoleFormState>,
  ): void {
    pendingScrollTopRef.current = captureRoleDetailScrollTop(pageRef.current);
    onUpdateRoleForm(next);
  }

  function updateChannelBindings(
    update: (bindings: RoleChannelBinding[]) => RoleChannelBinding[],
  ): void {
    preserveScrollDuringFormUpdate((current) => {
      const channelBindings = update(current.channelBindings ?? []);
      const targetChannel = current.proactiveTargetChannel ?? "";
      const targetChatId = current.proactiveTargetChatId ?? "";
      const targetStillBound = Boolean(targetChannel && targetChatId)
        && channelBindings.some(
          (binding) => binding.channel === targetChannel && binding.chat_id === targetChatId,
        );
      return {
        ...current,
        channelBindings,
        proactiveTargetChannel: targetStillBound ? targetChannel : "",
        proactiveTargetChatId: targetStillBound ? targetChatId : "",
      };
    });
  }

  const channelBindings = roleForm.channelBindings ?? [];
  const selectedProactiveBinding = channelBindings.find(
    (binding) => binding.channel === (roleForm.proactiveTargetChannel ?? "")
      && binding.chat_id === (roleForm.proactiveTargetChatId ?? ""),
  );
  const proactiveTransportSequence = selectedProactiveBinding
    ? buildProactiveTransportSequence(
      channelBindings,
      roleForm.proactiveTargetChannel ?? "",
      roleForm.proactiveTargetChatId ?? "",
    )
    : [];

  return (
    <section
      ref={pageRef}
      className="role-detail-page scrollbar-soft scrollbar-soft-accent relative h-full overflow-y-auto bg-white"
      data-testid="role-detail-page"
      data-has-featured-image={chatBackgroundUrl ? "true" : "false"}
    >
      {chatBackgroundUrl ? (
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: `url("${chatBackgroundUrl}")` }}
          data-testid="role-illustration-hero"
        />
      ) : (
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)]" data-testid="role-illustration-hero" />
      )}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.04)_0%,rgba(255,255,255,0.06)_18%,rgba(255,255,255,0.18)_100%)]" />
      <div className="relative mx-auto flex w-full max-w-[1120px] flex-col gap-5 px-8 pb-8 pt-8">
        <div className="flex items-start justify-between gap-4">
          <button
            data-testid="role-detail-back-button"
            className="grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] hover:shadow-[0_14px_28px_rgba(15,23,42,0.14)]"
            type="button"
            onClick={onBackToList}
            aria-label="返回角色列表"
          >
            {backIcon}
          </button>
          <div className="flex items-center gap-2.5">
            <button
              className={cx(floatingActionClass, "border-black/8 text-[#747474] hover:border-black/14 hover:bg-[#F5F7FA] hover:text-[#4f4f4f]")}
              type="button"
              onClick={onResetRoleForm}
              disabled={!roleFormDirty}
              aria-label="重置角色表单"
            >
              <ResetIcon className="h-[18px] w-[18px] fill-current" />
            </button>
            <button
              data-testid="save-role-button"
              className={cx(floatingActionClass, "border-transparent bg-white text-[#1f1f1f] hover:bg-[#F5F7FA]")}
              type="button"
              onClick={onSaveRole}
              disabled={savingRole || !roleFormDirty || !bridgeReady}
              aria-label={savingRole ? "正在保存角色" : "保存角色"}
            >
              <SaveIcon className="h-5 w-5 fill-current" />
            </button>
          </div>
        </div>
        <div className="p-2" data-testid="role-detail-info-card">
          <div className="grid gap-5 md:grid-cols-[116px_minmax(0,1fr)]">
            <button
              type="button"
              data-testid="open-role-assets-button"
              data-has-preview-avatar={previewAvatar ? "true" : "false"}
              className={cx(
                "group relative h-[116px] w-[116px] overflow-hidden rounded-[28px] border border-white/22 bg-[rgba(255,255,255,0.08)] text-left shadow-[0_14px_32px_rgba(15,23,42,0.14)] transition hover:scale-[1.01]",
                focusResetClass,
              )}
              onClick={onOpenAssetsPage}
            >
              {previewAvatar ? (
                <img className="h-full w-full object-cover" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
              ) : (
                <div className="grid h-full w-full place-items-center text-[34px] font-semibold text-white">
                  {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "R"}
                </div>
              )}
            </button>
            <div className="grid gap-4">
              <label className="grid gap-1.5 text-xs text-[#374151]">
                <span>名称</span>
                <input
                  data-testid="edit-role-name"
                  className={cx(inputClass, "border-[#D8DFE7] bg-white/82 text-[#111827] placeholder:text-[#9CA3AF]")}
                  value={roleForm.name}
                  onChange={(event) => preserveScrollDuringFormUpdate((current) => ({ ...current, name: event.target.value }))}
                  placeholder="输入角色名称"
                />
              </label>
              <label className="grid gap-1.5 text-xs text-[#374151]">
                <span>简介</span>
                <input
                  data-testid="edit-role-description"
                  className={cx(inputClass, "border-[#D8DFE7] bg-white/82 text-[#111827] placeholder:text-[#9CA3AF]")}
                  value={roleForm.description}
                  onChange={(event) => preserveScrollDuringFormUpdate((current) => ({ ...current, description: event.target.value }))}
                  placeholder="简短描述这个角色"
                />
              </label>
              <label className="grid gap-2 text-xs text-[#374151]" data-testid="role-detail-form-panel">
                <span>系统提示词</span>
                <textarea
                  ref={promptRef}
                  data-testid="edit-role-prompt"
                  className={cx(inputClass, "min-h-[20px] resize-none overflow-hidden border-[#D8DFE7] bg-white/82 text-[#111827] placeholder:text-[#9CA3AF]")}
                  value={roleForm.systemPrompt}
                  onChange={(event) => preserveScrollDuringFormUpdate((current) => ({ ...current, systemPrompt: event.target.value }))}
                  placeholder="定义这个角色的行为、语气和边界"
                />
              </label>
              <label className="flex items-center gap-3 text-xs text-[#374151]">
                <input
                  className={cx("h-4 w-4 rounded border-[#D8DFE7] text-[#111827]", focusResetClass)}
                  type="checkbox"
                  checked={roleForm.nsfwMemoryEnabled}
                  onChange={(event) => preserveScrollDuringFormUpdate((current) => ({ ...current, nsfwMemoryEnabled: event.target.checked }))}
                />
                <span>NSFW 记忆</span>
              </label>
              <div className="flex items-center justify-between gap-3 text-xs text-[#374151]">
                <span>自动场景 CG</span>
                <SettingsToggleCard
                  checked={roleForm.autoSceneCgEnabled}
                  ariaLabel="自动场景 CG"
                  onChange={(checked) => preserveScrollDuringFormUpdate((current) => ({ ...current, autoSceneCgEnabled: checked }))}
                />
              </div>
              <div className="grid gap-3 rounded-md border border-[#D8DFE7] bg-white/82 p-4 text-xs text-[#374151]" data-testid="role-channel-config">
                <div className="flex items-center justify-between gap-3">
                  <span>渠道绑定</span>
                  <button
                    className="rounded-md border border-[#D8DFE7] px-2 py-1 transition hover:border-primary"
                    type="button"
                    onClick={() => updateChannelBindings((bindings) => [...bindings, createRoleChannelBinding(activeRoleId)])}
                  >
                    添加
                  </button>
                </div>
                {channelBindings.map((binding, index) => (
                  <div className="grid gap-2 rounded-md border border-[#E4EAF0] p-3" key={`${binding.channel}:${binding.chat_id}:${index}`}>
                    <div className="grid gap-2 md:grid-cols-[120px_minmax(0,1fr)_auto_auto]">
                      <select
                        className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")}
                        value={binding.channel}
                        onChange={(event) => updateChannelBindings((bindings) => bindings.map((item, itemIndex) => itemIndex === index ? changeRoleBindingChannel(item, event.target.value, activeRoleId) : item))}
                      >
                        <option value="telegram">Telegram</option>
                        <option value="qq">QQ</option>
                        <option value="desktop">桌面端</option>
                      </select>
                      <input
                        className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")}
                        value={binding.chat_id}
                        placeholder="会话 / 群组 ID"
                        readOnly={isDesktopRoleBinding(binding)}
                        onChange={(event) => updateChannelBindings((bindings) => bindings.map((item, itemIndex) => itemIndex === index ? { ...item, chat_id: event.target.value } : item))}
                      />
                      <div className="flex items-center justify-end gap-1">
                        <button
                          className="grid h-8 w-8 place-items-center rounded-md border border-[#D8DFE7] text-[#667085] transition hover:border-primary hover:text-primary disabled:cursor-default disabled:opacity-35"
                          type="button"
                          onClick={() => updateChannelBindings((bindings) => moveRoleChannelBinding(bindings, index, "up"))}
                          disabled={index === 0}
                          aria-label={`上移${roleBindingChannelLabel(binding.channel)}绑定`}
                          title="上移"
                        >
                          <ArrowUpIcon className="h-4 w-4 stroke-current" />
                        </button>
                        <button
                          className="grid h-8 w-8 place-items-center rounded-md border border-[#D8DFE7] text-[#667085] transition hover:border-primary hover:text-primary disabled:cursor-default disabled:opacity-35"
                          type="button"
                          onClick={() => updateChannelBindings((bindings) => moveRoleChannelBinding(bindings, index, "down"))}
                          disabled={index === channelBindings.length - 1}
                          aria-label={`下移${roleBindingChannelLabel(binding.channel)}绑定`}
                          title="下移"
                        >
                          <ArrowDownIcon className="h-4 w-4 stroke-current" />
                        </button>
                      </div>
                      <button
                        className="grid h-8 w-8 place-items-center rounded-md border border-transparent text-[#a33] transition hover:border-[#eccaca] hover:text-[#711]"
                        type="button"
                        onClick={() => updateChannelBindings((bindings) => bindings.filter((_, itemIndex) => itemIndex !== index))}
                        aria-label={`移除${roleBindingChannelLabel(binding.channel)}绑定`}
                        title="移除"
                      >
                        <DeleteIcon className="h-4 w-4 fill-current" />
                      </button>
                    </div>
                    {!isDesktopRoleBinding(binding) ? (
                      <label className="grid gap-1.5">
                        <span>{roleBindingAllowFromLabel(binding.channel)}</span>
                        <input
                          className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")}
                          value={binding.allow_from.join(", ")}
                          onChange={(event) => updateChannelBindings((bindings) => bindings.map((item, itemIndex) => itemIndex === index ? { ...item, allow_from: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) } : item))}
                        />
                      </label>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="grid gap-3 rounded-md border border-[#D8DFE7] bg-white/82 p-4 text-xs text-[#374151]" data-testid="role-proactive-config">
                <label className="flex items-center gap-3">
                  <input className={cx("h-4 w-4 rounded border-[#D8DFE7] text-[#111827]", focusResetClass)} type="checkbox" checked={Boolean(roleForm.proactiveEnabled)} onChange={(event) => preserveScrollDuringFormUpdate((current) => ({ ...current, proactiveEnabled: event.target.checked }))} />
                  <span>主动推送</span>
                </label>
                <label className="grid gap-1.5">
                  <span>首选渠道</span>
                  <select
                    className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")}
                    value={`${roleForm.proactiveTargetChannel ?? ""}:${roleForm.proactiveTargetChatId ?? ""}`}
                    onChange={(event) => {
                      const selected = channelBindings.find((binding) => `${binding.channel}:${binding.chat_id}` === event.target.value);
                      preserveScrollDuringFormUpdate((current) => ({ ...current, proactiveTargetChannel: selected?.channel ?? "", proactiveTargetChatId: selected?.chat_id ?? "" }));
                    }}
                  >
                    <option value=":">未选择</option>
                    {channelBindings.filter((binding) => binding.chat_id.trim()).map((binding) => <option key={`${binding.channel}:${binding.chat_id}`} value={`${binding.channel}:${binding.chat_id}`}>{roleBindingChannelLabel(binding.channel)} · {binding.chat_id}</option>)}
                  </select>
                </label>
                {selectedProactiveBinding ? (
                  <ol className="grid gap-1.5" data-testid="role-proactive-sequence">
                    {proactiveTransportSequence.map((binding, index) => (
                      <li className="flex min-w-0 items-center gap-2" key={`${binding.channel}:${binding.chat_id}`}>
                        <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[#EEF2F6] text-[11px] text-[#667085]">{index + 1}</span>
                        <span className="min-w-0 truncate text-[#374151]">{roleBindingChannelLabel(binding.channel)} · {binding.chat_id}</span>
                        <span className="ml-auto shrink-0 text-[11px] text-[#98A2B3]">{index === 0 ? "首选" : "无回复后尝试 · 5 分钟"}</span>
                      </li>
                    ))}
                  </ol>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
