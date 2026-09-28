import { useState } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { compactPrimaryButtonClass, textareaClass } from "../shared/styles";
import { createAccountClient, type AccountResponseRules, type AccountSnapshot } from "./accountClient";

const client = createAccountClient();

/** Edits an account's account-wide response rules; its plugin saves them. */
export function AccountResponseRulesEditor({ account, onChanged }: { account: AccountSnapshot; onChanged: () => void }) {
  const [rules, setRules] = useState<AccountResponseRules>(account.responseRules);
  const [blockedText, setBlockedText] = useState(rules.blockedSenderIds.join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  // Group settings show for group-capable accounts, or when they already hold non-default values.
  const showGroups = account.capabilities.includes("groups") ||
    !rules.groupEnabled || !rules.requireMention || rules.blockedSenderIds.length > 0;

  async function save() {
    setBusy(true);
    setError("");
    try {
      const next = { ...rules, blockedSenderIds: blockedText.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) };
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

  return <section className="grid gap-4" aria-label="响应规则">
    <h3 className="m-0 text-body font-medium text-ink">响应规则</h3>
    {error ? <InlineError message={error} /> : null}
    <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
      <input type="checkbox" checked={rules.privateEnabled} onChange={(event) => { setSaved(false); setRules((current) => ({ ...current, privateEnabled: event.target.checked })); }} />私聊启用
    </label>
    {showGroups ? <>
      <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
        <input type="checkbox" checked={rules.groupEnabled} onChange={(event) => { setSaved(false); setRules((current) => ({ ...current, groupEnabled: event.target.checked })); }} />群聊启用
      </label>
      <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
        <input type="checkbox" checked={rules.requireMention} disabled={!rules.groupEnabled} onChange={(event) => { setSaved(false); setRules((current) => ({ ...current, requireMention: event.target.checked })); }} />群聊需要 @
      </label>
      <label className="grid gap-2 text-body-sm text-ink-secondary">黑名单成员 ID
        <textarea className={textareaClass} rows={3} value={blockedText} onChange={(event) => { setSaved(false); setBlockedText(event.target.value); }} />
      </label>
    </> : null}
    <div className="flex items-center gap-3">
      <button type="button" className={compactPrimaryButtonClass} disabled={busy} onClick={() => void save()}>保存规则</button>
      {saved ? <span role="status" className="text-body-sm text-ink-muted">已保存</span> : null}
    </div>
  </section>;
}
