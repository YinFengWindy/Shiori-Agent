import React, { useCallback, useEffect, useState } from "react";
import type { PluginAccountDetailComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { ghostButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";

type Draft = { ref: string; mode?: "external" | "managed"; ws_uri: string; expected_uin: string; verified: boolean; auto_connect: boolean; connection: string; error: string; role_id: string };
type EditorProps = PluginAccountDetailComponentProps & { draftRef?: string };

/**
 * The add-account flow on a role's page: that role's saved, unverified QQ
 * drafts (待连接), and the form for a selected draft or a new one.
 */
export function QQDraftsSection({ roleId, client, host, onChanged, Editor }: Omit<PluginAccountDetailComponentProps, "account"> & {
  Editor: React.ComponentType<EditorProps>;
}) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    try {
      const result = await client.call<{ accounts: Draft[] }>("accounts.settings");
      // Drafts remember the role they were started from; show only this role's.
      setDrafts(result.accounts.filter((row) => !row.verified && row.role_id === roleId));
      setError("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [client, roleId]);
  useEffect(() => { void reload(); const timer = window.setInterval(() => void reload(), 5000); return () => window.clearInterval(timer); }, [reload]);

  async function remove(ref: string) {
    setBusy(ref);
    setError("");
    try {
      await client.call("accounts.remove_draft", { ref });
      if (selected === ref) setSelected("");
      await reload();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy("");
    }
  }

  return <div className="grid gap-4">
    {error ? <host.ui.InlineError message={error} /> : null}
    {drafts.length ? <section className="grid gap-2" aria-label="待连接的 QQ 配置">
      <h3 className="m-0 text-body font-semibold text-ink">待连接</h3>
      {drafts.map((draft) => <div key={draft.ref} className="flex items-center justify-between gap-3 border-b border-line-soft py-2">
        <span className="min-w-0 break-all text-body-sm text-ink-secondary">{draft.expected_uin ? `${draft.expected_uin} · ` : ""}{draft.mode === "managed" ? "托管 NapCat" : draft.ws_uri}<span className="block text-ink-muted">{draft.connection}{draft.error ? ` · ${draft.error}` : ""}</span></span>
        <div className="flex shrink-0 gap-2">
          <button type="button" className={ghostButtonClass} onClick={() => setSelected(draft.ref)} disabled={Boolean(busy) || selected === draft.ref}>编辑</button>
          {!draft.auto_connect ? <button type="button" className={ghostButtonClass} onClick={() => void remove(draft.ref)} disabled={Boolean(busy)}>移除</button> : null}
        </div>
      </div>)}
      {selected ? <div><button type="button" className={ghostButtonClass} onClick={() => setSelected("")}>新建</button></div> : null}
    </section> : null}
    <Editor key={selected || "new"} draftRef={selected} account={null} roleId={roleId} client={client} host={host}
      onChanged={(accountId) => { if (accountId) onChanged(accountId); else void reload(); }} />
  </div>;
}
