import { PhoneDailyCapField } from "./PhoneDailyCapField";
import { PhoneLoadError } from "./PhoneLoadError";
import { PhoneScreenHeader } from "./PhoneScreenHeader";
import { usePhoneListeningDefaultCap } from "./usePhoneListening";

/** The phone's settings, opened from the home screen: the default daily cap of group listening. */
export function PhoneSettingsPage({ onBack }: { onBack: () => void }) {
  const { defaultCap, error, retry, save } = usePhoneListeningDefaultCap();
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <PhoneScreenHeader title="设置" backLabel="返回主屏幕" onBack={onBack} focusBack />
      <div className="grid min-h-0 content-start gap-2.5 overflow-y-auto p-2.5" data-testid="phone-settings">
        <section className="surface-glass grid min-w-0 gap-1.5 rounded-md p-2.5" aria-label="旁听">
          <h4 className="m-0 px-0.5 text-caption font-semibold text-ink-muted">旁听</h4>
          {error ? <PhoneLoadError message={error} onRetry={() => void retry()} />
            : defaultCap === null ? null
              : (
                <PhoneDailyCapField stored={defaultCap} label="默认每日上限" testId="phone-settings-default-cap"
                  onSave={async (dailyCap) => {
                    // The field requires a number here; blank never passes its check.
                    if (dailyCap === null) throw new Error("默认每日上限不能为空");
                    await save(dailyCap);
                  }} />
              )}
        </section>
      </div>
    </div>
  );
}
