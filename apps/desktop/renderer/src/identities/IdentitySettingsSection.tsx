import { useAccounts } from "../accounts/useAccounts";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { InlineError } from "../shared/feedback/InlineError";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { compactGhostButtonClass } from "@yinfengwindy/shiori-sdk";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { settingsGroupStackClass } from "../settings/SettingsFieldPrimitives";
import { IdentityList } from "./IdentityList";
import { identityChannel } from "./identityPresentation";
import { PairingCodePanel } from "./PairingCodePanel";
import { useIdentities } from "./useIdentities";
import { useIdentityUnbind } from "./useIdentityUnbind";
import { usePairingCode } from "./usePairingCode";

/** Every plugin's channel name and mark, enabled or not: a binding outlives its plugin being off. */
const allPlugins = () => true;

/** Settings › 我的身份: the pairing card and the identities it has bound. */
export function IdentitySettingsSection() {
  const pairing = usePairingCode();
  // A new binding means the shown code was just consumed.
  const { identities, error, reload } = useIdentities(pairing.clear);
  const { accounts } = useAccounts();
  const unbind = useIdentityUnbind(() => void reload());
  const channels = pluginUiRegistry.listAccountDetails(allPlugins);
  const pending = unbind.pending;
  return <div className={settingsGroupStackClass}>
    <PairingCodePanel code={pairing.code} remainingMs={pairing.remainingMs} busy={pairing.busy}
      error={pairing.error} onCreate={() => void pairing.create()} />
    {error ? <InlineError message={error}
      actions={<button type="button" className={compactGhostButtonClass} onClick={() => void reload()}>重试</button>} /> : null}
    {identities?.length ? <IdentityList identities={identities} channels={channels} accounts={accounts} onUnbind={unbind.request} /> : null}
    <ConfirmDialog
      open={Boolean(pending)}
      title="解除绑定"
      persona={confirmPersonaLines.destructive}
      description={pending ? `${identityChannel(pending, channels).label} ${pending.userId} 发来的消息将不再被认作你。` : ""}
      confirmLabel="解除绑定"
      busy={unbind.busy}
      busyLabel="解除中..."
      error={unbind.error}
      onClose={unbind.cancel}
      onConfirm={() => void unbind.confirm()}
    />
  </div>;
}
