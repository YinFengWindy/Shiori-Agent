import { SettingsField } from "@yinfengwindy/shiori-sdk";
import { IntegerField } from "./IntegerField";
import type { LiveConfig } from "./liveContracts";
import type { LiveConfigAutosave } from "./useLiveConfig";

type LiveConfigFieldsProps = {
  draft: LiveConfig;
  update: LiveConfigAutosave["update"];
  disabled: boolean;
};

/** The room and the two timings, in the ranges `backend/live_config.py` accepts; each edit autosaves. */
export function LiveConfigFields({ draft, update, disabled }: LiveConfigFieldsProps) {
  const set = (change: Partial<LiveConfig>) => update((current) => ({ ...current, ...change }));
  return <>
    <SettingsField label="直播间号">
      <IntegerField label="直播间号" value={draft.room_id} min={1} optional disabled={disabled}
        onChange={(room_id) => set({ room_id })} />
    </SettingsField>
    <SettingsField label="回复间隔（秒）">
      <IntegerField label="回复间隔（秒）" value={draft.reply_interval_seconds} min={0} max={300} disabled={disabled}
        onChange={(seconds) => { if (seconds !== null) set({ reply_interval_seconds: seconds }); }} />
    </SettingsField>
    <SettingsField label="等待时限（秒）">
      <IntegerField label="等待时限（秒）" value={draft.wait_timeout_seconds} min={5} max={600} disabled={disabled}
        onChange={(seconds) => { if (seconds !== null) set({ wait_timeout_seconds: seconds }); }} />
    </SettingsField>
  </>;
}
