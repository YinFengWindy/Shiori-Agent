import { useState } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { textareaClass } from "../shared/styles";
import { createAccountClient, type AccountResponseRules, type AccountSnapshot } from "./accountClient";

const client = createAccountClient();

function parseIds(text: string) {
  return text.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function sameIds(a: string[], b: string[]) {
  return a.length === b.length && a.every((item, index) => item === b[index]);
}

/**
 * Edits an account's account-wide response rules; its plugin saves them.
 * Every change saves on its own — a checkbox at once, the blacklist when the
 * field loses focus — and a failed save shows why and puts the last saved
 * value back.
 */
export function AccountResponseRulesEditor({ account, onChanged }: { account: AccountSnapshot; onChanged: () => void }) {
  const [saved, setSaved] = useState<AccountResponseRules>(account.responseRules);
  const [rules, setRules] = useState<AccountResponseRules>(account.responseRules);
  const [blockedText, setBlockedText] = useState(account.responseRules.blockedSenderIds.join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Group settings show for group-capable accounts, or when they already hold non-default values.
  const showGroups = account.capabilities.includes("groups") ||
    !rules.groupEnabled || !rules.requireMention || rules.blockedSenderIds.length > 0;

  async function save(next: AccountResponseRules) {
    setRules(next);
    setBusy(true);
    setError("");
    try {
      await client.setRules(account.id, next);
      setSaved(next);
      onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      setRules(saved);
      setBlockedText(saved.blockedSenderIds.join("\n"));
    } finally {
      setBusy(false);
    }
  }

  function toggle(field: "privateEnabled" | "groupEnabled" | "requireMention", checked: boolean) {
    void save({ ...rules, [field]: checked });
  }

  function commitBlocked() {
    const ids = parseIds(blockedText);
    if (!sameIds(ids, saved.blockedSenderIds)) void save({ ...rules, blockedSenderIds: ids });
  }

  return <section className="grid gap-4" aria-label="响应规则" aria-busy={busy || undefined}>
    <h3 className="m-0 text-body font-medium text-ink">响应规则</h3>
    {error ? <InlineError message={error} /> : null}
    <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
      <input type="checkbox" checked={rules.privateEnabled} disabled={busy} onChange={(event) => toggle("privateEnabled", event.target.checked)} />私聊启用
    </label>
    {showGroups ? <>
      <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
        <input type="checkbox" checked={rules.groupEnabled} disabled={busy} onChange={(event) => toggle("groupEnabled", event.target.checked)} />群聊启用
      </label>
      <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
        <input type="checkbox" checked={rules.requireMention} disabled={busy || !rules.groupEnabled} onChange={(event) => toggle("requireMention", event.target.checked)} />群聊需要 @
      </label>
      <label className="grid gap-2 text-body-sm text-ink-secondary">黑名单成员 ID
        <textarea className={textareaClass} rows={3} value={blockedText} disabled={busy}
          onChange={(event) => setBlockedText(event.target.value)} onBlur={commitBlocked} />
      </label>
    </> : null}
  </section>;
}
