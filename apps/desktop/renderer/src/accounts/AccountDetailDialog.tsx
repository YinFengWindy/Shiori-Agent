import { Dialog } from "@base-ui/react/dialog";
import { XIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { InlineError } from "../shared/feedback/InlineError";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { ghostButtonClass, iconButtonClass } from "../shared/styles";
import { Select } from "../shared/ui/Select";
import type { RoleRecord } from "../shared/types";
import { accountStatus } from "./accountPresentation";
import { createAccountClient, type AccountSnapshot } from "./accountClient";
import { AccountResponseRulesEditor } from "./AccountResponseRulesEditor";

const client = createAccountClient();

/** Shared host detail for both role and plugin entry points. Platform controls use account.detail. */
export function AccountDetailDialog({ account, pluginId, onClose, onChanged }: {
  account: AccountSnapshot | null;
  pluginId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [roles, setRoles] = useState<Pick<RoleRecord, "id" | "name">[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    void invokeBridgePayload<{ roles: RoleRecord[] }>(window.miraDesktop.invoke, "roles.list", {})
      .then((result) => setRoles(result.roles.map(({ id, name }) => ({ id, name }))))
      .catch((failure) => setError(failure instanceof Error ? failure.message : String(failure)));
  }, []);
  const pluginControls = pluginUiRegistry.getAccountDetail(pluginId, () => account?.pluginEnabled ?? true);
  const PlatformControls = pluginControls?.Component;

  async function mutate(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return <Dialog.Root open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className="confirm-dialog-backdrop motion-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
      <Dialog.Popup className="confirm-dialog motion-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[min(42rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-md border border-line bg-surface p-6 shadow-panel">
        <div className="flex items-start justify-between gap-3 border-b border-line-soft pb-4">
          <div className="min-w-0">
            <Dialog.Title className="font-display text-title font-semibold text-ink">{account?.displayName || account?.platformAccountId || "添加账号"}</Dialog.Title>
            {account ? <p className="m-0 break-all text-body-sm text-ink-muted">{account.platform} · {account.platformAccountId} · {accountStatus(account)}</p> : null}
          </div>
          <Dialog.Close className={iconButtonClass} aria-label="关闭账号详情" disabled={busy}><XIcon className="h-5 w-5" /></Dialog.Close>
        </div>
        <div className="scrollbar-stable grid min-h-0 gap-6 overflow-y-auto py-5">
          {error ? <InlineError message={error} /> : null}
          {account?.error && account.connection === "error" ? <InlineError message={account.error} /> : null}
          {account ? <>
            <label className="grid gap-2 text-body-sm text-ink-secondary">
              所属角色
              <Select aria-label="所属角色" value={account.roleId ?? ""} disabled={busy} options={[
                { value: "", label: "未分配" }, ...roles.map((role) => ({ value: role.id, label: role.name })),
              ]} onValueChange={(value) => void mutate(() => client.assign(account.id, value || null))} />
            </label>
            <AccountResponseRulesEditor account={account} onChanged={onChanged} />
          </> : null}
          {PlatformControls ? <section className="border-t border-line-soft pt-5" aria-label="平台设置">
            <PlatformControls account={account} onChanged={onChanged} />
          </section> : null}
        </div>
        <div className="flex justify-end border-t border-line-soft pt-4"><button type="button" className={ghostButtonClass} onClick={onClose}>关闭</button></div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
