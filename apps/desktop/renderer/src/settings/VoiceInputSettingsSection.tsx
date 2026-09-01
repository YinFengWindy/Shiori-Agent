import { useEffect, useRef, useState } from "react";
import { Microphone, Stop } from "@phosphor-icons/react";
import type { VoiceInputDevice } from "../../../src/bridge/shared.js";
import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSectionCard,
  SettingsToggleField,
  settingsIconButtonClass,
  settingsInputClass,
} from "./SettingsFieldPrimitives";
import type { SettingsFormData } from "../../../src/bridge/shared.js";
import type { SettingsDraftUpdater } from "./settingsPageTypes";
import { cx } from "../shared/styles";

type VoiceInputSettingsSectionProps = {
  draft: Pick<SettingsFormData, "voice">;
  updateDraft: SettingsDraftUpdater;
};

/** Owns microphone enumeration and the bounded test-recording lifecycle. */
export function VoiceInputSettingsSection({ draft, updateDraft }: VoiceInputSettingsSectionProps) {
  const [devices, setDevices] = useState<VoiceInputDevice[]>([]);
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState("");
  const testTimer = useRef<number | null>(null);
  const testActive = useRef(false);

  useEffect(() => {
    if (typeof window.miraDesktop.listVoiceInputDevices !== "function") return undefined;
    void window.miraDesktop.listVoiceInputDevices().then(setDevices).catch((error) => {
      setTestError(error instanceof Error ? error.message : String(error));
    });
    return () => {
      if (testTimer.current !== null) window.clearTimeout(testTimer.current);
      testTimer.current = null;
      if (testActive.current) {
        testActive.current = false;
        void window.miraDesktop.cancelVoiceTest();
      }
    };
  }, []);

  async function toggleTestRecording(): Promise<void> {
    setTestError("");
    try {
      if (testing) {
        if (testTimer.current !== null) window.clearTimeout(testTimer.current);
        testTimer.current = null;
        testActive.current = false;
        await window.miraDesktop.stopVoiceTest();
        setTesting(false);
        return;
      }
      testActive.current = true;
      await window.miraDesktop.startVoiceTest(draft.voice.microphoneDeviceId || undefined);
      setTesting(true);
      testTimer.current = window.setTimeout(() => {
        testTimer.current = null;
        testActive.current = false;
        void window.miraDesktop.stopVoiceTest()
          .catch((error) => setTestError(error instanceof Error ? error.message : String(error)))
          .finally(() => setTesting(false));
      }, 3000);
    } catch (error) {
      testActive.current = false;
      setTesting(false);
      setTestError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <SettingsSectionCard>
      <SettingsToggleField
        label="启用桌宠语音"
        checked={draft.voice.enabled}
        onChange={(checked) => updateDraft((current) => ({ ...current, voice: { ...current.voice, enabled: checked } }))}
      />
      <Field label="全局快捷键">
        <input
          className={settingsInputClass}
          value={draft.voice.hotkey}
          onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, hotkey: event.target.value } }))}
          placeholder="Ctrl+Space"
        />
      </Field>
      <Field label="麦克风设备">
        <div className="flex min-w-0 items-center gap-2">
          <select
            className={cx(settingsInputClass, "min-w-0 flex-1")}
            value={draft.voice.microphoneDeviceId}
            onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, microphoneDeviceId: event.target.value } }))}
          >
            <option value="">系统默认设备</option>
            {devices.map((device) => <option key={device.deviceId} value={device.deviceId}>{device.label || device.deviceId}</option>)}
          </select>
          <button
            className={cx(settingsIconButtonClass, testing && "text-[#C83E3E] hover:bg-[#FFF1F1] hover:text-[#C83E3E]")}
            type="button"
            aria-label={testing ? "停止麦克风测试" : "测试麦克风"}
            title={testing ? "停止麦克风测试" : "测试麦克风"}
            onClick={() => void toggleTestRecording()}
          >
            {testing ? <Stop className="h-3.5 w-3.5 fill-current" weight="bold" /> : <Microphone className="h-3.5 w-3.5" weight="bold" />}
          </button>
        </div>
      </Field>
      {testError ? <div className="text-[11px] text-[#8f2d2d]">{testError}</div> : null}
    </SettingsSectionCard>
  );
}
