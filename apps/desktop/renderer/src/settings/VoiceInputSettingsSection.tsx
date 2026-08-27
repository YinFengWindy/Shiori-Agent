import { useEffect, useRef, useState } from "react";
import type { VoiceInputDevice } from "../../../src/bridge/shared.js";
import { SettingsField as Field } from "./SettingsField";
import { SettingsSectionCard, SettingsToggleField, settingsInputClass } from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";

type VoiceInputSettingsSectionProps = Pick<SettingsSectionEditorProps, "draft" | "updateDraft">;

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

  async function refreshDevices(): Promise<void> {
    setTestError("");
    try {
      setDevices(await window.miraDesktop.listVoiceInputDevices());
    } catch (error) {
      setTestError(error instanceof Error ? error.message : String(error));
    }
  }

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
        <select
          className={settingsInputClass}
          value={draft.voice.microphoneDeviceId}
          onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, microphoneDeviceId: event.target.value } }))}
        >
          <option value="">系统默认设备</option>
          {devices.map((device) => <option key={device.deviceId} value={device.deviceId}>{device.label || device.deviceId}</option>)}
        </select>
      </Field>
      <div className="flex flex-wrap gap-2">
        <button className="rounded-md border border-[#D8DCE2] px-3 py-2 text-sm transition hover:border-primary" type="button" onClick={() => void refreshDevices()}>刷新设备</button>
        <button className="rounded-md border border-[#D8DCE2] px-3 py-2 text-sm transition hover:border-primary" type="button" onClick={() => void toggleTestRecording()}>{testing ? "停止并播放" : "测试录音"}</button>
      </div>
      {testError ? <div className="text-xs text-[#8f2d2d]">{testError}</div> : null}
    </SettingsSectionCard>
  );
}
