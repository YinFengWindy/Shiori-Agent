import { SettingsToggleCard } from "@yinfengwindy/shiori-sdk";
import { InlineError } from "../shared/feedback/InlineError";
import { useBusyAction } from "../shared/useBusyAction";
import type { PhoneChatInfoSectionProps } from "./PhoneChatInfoSections";
import { PhoneDailyCapField } from "./PhoneDailyCapField";
import { phoneListeningToggleRows } from "./phoneListening";
import { PhoneLoadError } from "./PhoneLoadError";
import { usePhoneListening } from "./usePhoneListening";

/**
 * 旁听: whether the role listens in on the group, the group's own daily
 * cap (blank follows the default from the phone's settings), and who turned
 * listening on or off when.
 */
export function PhoneListeningSection({ section, roleId, roleName, conversation, now }: PhoneChatInfoSectionProps) {
  const { state, error, retry, setEnabled, setDailyCap } = usePhoneListening(roleId, conversation.threadId);
  const switching = useBusyAction();
  if (error) return <PhoneLoadError message={error} onRetry={() => void retry()} />;
  if (!state) return null;
  const toggles = phoneListeningToggleRows(state.toggles, roleName, now);
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2 px-0.5">
        <span className="text-body-sm text-ink">旁听本群</span>
        <SettingsToggleCard compact checked={state.enabled} disabled={switching.busy} ariaLabel={section.title}
          onChange={(enabled) => void switching.run(() => setEnabled(enabled))} />
      </div>
      {switching.error ? <InlineError message={switching.error} persona={false} /> : null}
      <PhoneDailyCapField stored={state.dailyCap} label="每日上限" placeholder={`默认 ${state.defaultDailyCap}`} allowBlank
        testId="phone-listening-cap" onSave={setDailyCap} />
      {toggles.length ? (
        <ul className="m-0 grid list-none gap-0.5 p-0" aria-label="开关记录" data-testid="phone-listening-toggles">
          {toggles.map(({ key, who, action, time }) => (
            <li key={key} className="flex min-w-0 items-baseline gap-1.5 px-0.5 text-caption text-ink-muted">
              <span className="min-w-0 truncate text-ink-secondary">{who}</span>
              <span className="shrink-0">{action}</span>
              <span className="ml-auto shrink-0 tabular-nums">{time}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
