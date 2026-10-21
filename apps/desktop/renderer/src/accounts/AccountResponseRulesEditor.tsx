import { errorMessage, useLatestRef } from "@yinfengwindy/shiori-sdk";
import { useState } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { SettingsToggleField, textareaClass, type AccountResponseRules, type AccountSnapshot } from "@yinfengwindy/shiori-sdk";
import { createAccountClient } from "./accountClient";

const client = createAccountClient();

type RuleMutation = { account: AccountSnapshot; patch: Partial<AccountResponseRules> };

function parseIds(text: string) {
  return text.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function sameIds(a: string[], b: string[]) {
  return a.length === b.length && a.every((item, index) => item === b[index]);
}

/**
 * Edits an account's account-wide response rules; its plugin saves them.
 * Every change saves on its own — a checkbox at once, the blacklist when the
 * field loses focus. Host snapshots own the rules; local state holds only an
 * in-flight field change and the unsaved blacklist text.
 */
export function AccountResponseRulesEditor({ account, onChanged }: { account: AccountSnapshot; onChanged: () => void | Promise<void> }) {
  const [pending, setPending] = useState<RuleMutation | null>(null);
  const [blockedDraft, setBlockedDraft] = useState<string | null>(null);
  const [error, setError] = useState("");
  const latest = useLatestRef({ account, onChanged });
  const busy = pending !== null;
  // Any newer host snapshot supersedes an optimistic change, even for the
  // same account ID: a replacement Bot may have revoked the previous grant.
  const rules = pending?.account === account ? { ...account.responseRules, ...pending.patch } : account.responseRules;
  const blockedText = blockedDraft ?? account.responseRules.blockedSenderIds.join("\n");
  // The group toggle only applies to accounts that serve group chats; the blacklist also covers private chats.
  const showGroups = account.capabilities.includes("groups");

  async function save(patch: Partial<AccountResponseRules>) {
    if (busy) return;
    const mutation = { account: latest.current.account, patch };
    const submittedDraft = blockedDraft;
    setPending(mutation);
    setError("");
    try {
      await client.setRules(mutation.account.id, { ...mutation.account.responseRules, ...patch });
      // The mutation's response may predate a rebind or another host update.
      // Refresh the owner instead of adopting that response as a new baseline.
      await latest.current.onChanged();
    } catch (failure) {
      setError(errorMessage(failure, { includeDetail: true }));
    } finally {
      setPending((current) => current === mutation ? null : current);
      if (patch.blockedSenderIds !== undefined) {
        setBlockedDraft((current) => current === submittedDraft ? null : current);
      }
    }
  }

  function toggle(field: "privateEnabled" | "groupEnabled" | "allowFullTools", checked: boolean) {
    void save({ [field]: checked });
  }

  function commitBlocked() {
    const ids = parseIds(blockedText);
    if (!sameIds(ids, account.responseRules.blockedSenderIds)) void save({ blockedSenderIds: ids });
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
    {account.capabilities.includes("full_tools") ? <SettingsToggleField label="允许完整工具权限"
      checked={rules.allowFullTools === true} disabled={busy}
      onChange={(checked) => toggle("allowFullTools", checked)} /> : null}
    <label className="grid gap-2 text-body-sm text-ink-secondary">黑名单成员 ID
      <textarea className={textareaClass} rows={3} value={blockedText} disabled={busy}
        onChange={(event) => setBlockedDraft(event.target.value)} onBlur={commitBlocked} />
    </label>
  </section>;
}
