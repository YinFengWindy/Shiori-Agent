import { useState } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { textareaClass, type AccountResponseRules, type AccountSnapshot } from "@shiori/plugin-sdk";
import { createAccountClient } from "./accountClient";

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
  // The group toggle only applies to accounts that serve group chats; the blacklist also covers private chats.
  const showGroups = account.capabilities.includes("groups");

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

  function toggle(field: "privateEnabled" | "groupEnabled", checked: boolean) {
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
    {showGroups ? <label className="flex items-center gap-3 text-body-sm text-ink-secondary">
      <input type="checkbox" checked={rules.groupEnabled} disabled={busy} onChange={(event) => toggle("groupEnabled", event.target.checked)} />群聊启用
    </label> : null}
    <label className="grid gap-2 text-body-sm text-ink-secondary">黑名单成员 ID
      <textarea className={textareaClass} rows={3} value={blockedText} disabled={busy}
        onChange={(event) => setBlockedText(event.target.value)} onBlur={commitBlocked} />
    </label>
  </section>;
}
