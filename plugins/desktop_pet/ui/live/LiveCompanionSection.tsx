import { compactGhostButtonClass, SettingsField, SettingsGroup, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { BilibiliLoginPanel } from "./BilibiliLoginPanel";
import { LiveConfigFields } from "./LiveConfigFields";
import { LiveRunPanel } from "./LiveRunPanel";
import { startBlockedReason } from "./liveStatusView";
import { useBilibiliAccount } from "./useBilibiliAccount";
import type { LiveConfigAutosave } from "./useLiveConfig";
import { useLiveRun } from "./useLiveRun";

type LiveCompanionSectionProps = {
  roleId: string;
  client: PluginRpcClient;
  /** Owned by the card, which submits the last edit when the dialog closes. */
  config: LiveConfigAutosave;
  /** The saved pet switch; an unsaved draft does not let a run start. */
  petEnabled: boolean;
  /** Whether the dialog is shown; polling runs only while it is. */
  open: boolean;
  disabled: boolean;
};

/**
 * 「直播陪伴」 in the pet card's dialog (#292, #725): the Bilibili login, the
 * autosaved room and timings, and the run. Login and run act at once through
 * their own RPCs; none of it joins the role editor's draft.
 */
export function LiveCompanionSection({ roleId, client, config, petEnabled, open, disabled }: LiveCompanionSectionProps) {
  const host = usePluginHostServices();
  const login = useBilibiliAccount(client, roleId, open);
  const run = useLiveRun(client, roleId, open);
  const blockedReason = startBlockedReason({ petEnabled, account: login.account, roomId: config.saved?.room_id ?? null });
  return <SettingsGroup title="直播陪伴">
    <SettingsField label="B 站账号" layout="stack"><BilibiliLoginPanel login={login} disabled={disabled} /></SettingsField>
    {config.loadError ? <SettingsField label="直播设置" layout="stack">
      <host.ui.InlineError message={config.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={config.reload}>重新加载</button>} />
    </SettingsField> : null}
    {config.saveError ? <SettingsField label="直播设置" layout="stack">
      <host.ui.InlineError message={config.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={config.retry}>重试</button>} />
    </SettingsField> : null}
    {config.draft ? <LiveConfigFields draft={config.draft} update={config.update} disabled={disabled} /> : null}
    <SettingsField label="运行" layout="stack"><LiveRunPanel run={run} blockedReason={blockedReason} disabled={disabled} /></SettingsField>
  </SettingsGroup>;
}
