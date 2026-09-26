import { useState } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { compactButtonSizeClass, cx, dangerGhostButtonSurfaceClass, ghostButtonClass, inputClass, primaryButtonClass, textareaClass } from "../shared/styles";
import { createAccountClient, type AccountResponseRules, type AccountSnapshot } from "./accountClient";

const client = createAccountClient();

/** Edits host-owned account defaults and group-specific overrides with explicit save. */
export function AccountResponseRulesEditor({ account, onChanged }: { account: AccountSnapshot; onChanged: () => void }) {
  const [rules, setRules] = useState<AccountResponseRules>(account.responseRules);
  const [blockedText, setBlockedText] = useState(rules.blockedSenderIds.join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const showGroups = account.knownCapabilities.includes("groups") || rules.groupRules.length > 0 ||
    !rules.groupEnabled || !rules.requireMention || rules.blockedSenderIds.length > 0;

  function updateGroup(index: number, patch: Partial<AccountResponseRules["groupRules"][number]>) {
    setSaved(false);
    setRules((current) => ({
      ...current,
      groupRules: current.groupRules.map((group, position) => position === index ? { ...group, ...patch } : group),
    }));
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      const next = { ...rules, blockedSenderIds: blockedText.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        groupRules: rules.groupRules.map((group) => ({ ...group, chatId: group.chatId.trim(), blockedSenderIds: group.blockedSenderIds.map((item) => item.trim()).filter(Boolean) })) };
      await client.setRules(account.id, next);
      setRules(next);
      setSaved(true);
      onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return <section className="grid gap-4 border-t border-line-soft pt-5" aria-label="响应规则">
    <h3 className="m-0 text-body font-medium text-ink">响应规则</h3>
    {error ? <InlineError message={error} /> : null}
    <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
      <input type="checkbox" checked={rules.privateEnabled} onChange={(event) => { setSaved(false); setRules((current) => ({ ...current, privateEnabled: event.target.checked })); }} />私聊启用
    </label>
    {showGroups ? <>
      <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
        <input type="checkbox" checked={rules.groupEnabled} onChange={(event) => { setSaved(false); setRules((current) => ({ ...current, groupEnabled: event.target.checked })); }} />其他群聊启用
      </label>
      <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
        <input type="checkbox" checked={rules.requireMention} disabled={!rules.groupEnabled} onChange={(event) => { setSaved(false); setRules((current) => ({ ...current, requireMention: event.target.checked })); }} />群聊需要 @
      </label>
      <label className="grid gap-2 text-body-sm text-ink-secondary">黑名单成员 ID
        <textarea className={textareaClass} rows={3} value={blockedText} onChange={(event) => { setSaved(false); setBlockedText(event.target.value); }} />
      </label>
      <div className="grid gap-3 border-t border-line-soft pt-3">
      <div className="flex items-center justify-between gap-2"><h4 className="m-0 text-body-sm font-medium text-ink">群规则</h4>
        <button type="button" className={ghostButtonClass} onClick={() => { setSaved(false); setRules((current) => ({ ...current, groupRules: [...current.groupRules, { chatId: "", enabled: true, requireMention: true, blockedSenderIds: [] }] })); }}>添加群</button>
      </div>
      {rules.groupRules.map((group, index) => <div key={index} className="grid gap-2 border-b border-line-soft pb-3 last:border-b-0">
        <input aria-label={`群 ${index + 1} 会话 ID`} className={inputClass} placeholder="会话 ID" value={group.chatId} onChange={(event) => updateGroup(index, { chatId: event.target.value })} />
        <div className="flex flex-wrap items-center gap-4 text-body-sm text-ink-secondary">
          <label><input type="checkbox" checked={group.enabled} onChange={(event) => updateGroup(index, { enabled: event.target.checked })} /> 启用</label>
          <label><input type="checkbox" checked={group.requireMention} onChange={(event) => updateGroup(index, { requireMention: event.target.checked })} /> 需要 @</label>
          <button type="button" className={cx(dangerGhostButtonSurfaceClass, compactButtonSizeClass)} onClick={() => { setSaved(false); setRules((current) => ({ ...current, groupRules: current.groupRules.filter((_, position) => position !== index) })); }}>移除</button>
        </div>
        <textarea aria-label={`群 ${index + 1} 黑名单成员 ID`} className={textareaClass} rows={2} value={group.blockedSenderIds.join("\n")} onChange={(event) => updateGroup(index, { blockedSenderIds: event.target.value.split(/\r?\n/) })} />
      </div>)}
      </div>
    </> : null}
    <div className="flex items-center gap-3">
      <button type="button" className={primaryButtonClass} disabled={busy} onClick={() => void save()}>保存规则</button>
      {saved ? <span role="status" className="text-body-sm text-ink-muted">已保存</span> : null}
    </div>
  </section>;
}
