import { useEffect, useRef, useState } from "react";
import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  SettingsToggleField,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { cx, inputClass } from "../shared/styles";
import type { VoiceInputDevice } from "../../../src/shared.js";

/** Renders global voice provider and input preferences. */
export function VoiceSettingsSection({ draft, subsectionId, updateDraft }: SettingsSectionEditorProps) {
  const [devices, setDevices] = useState<VoiceInputDevice[]>([]);
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState("");
  const testTimer = useRef<number | null>(null);

  useEffect(() => {
    if (subsectionId !== "input" || typeof window.miraDesktop.listVoiceInputDevices !== "function") return undefined;
    void window.miraDesktop.listVoiceInputDevices().then(setDevices).catch((error) => {
      setTestError(error instanceof Error ? error.message : String(error));
    });
    return () => {
      if (testTimer.current !== null) window.clearTimeout(testTimer.current);
      testTimer.current = null;
    };
  }, [subsectionId]);

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
        await window.miraDesktop.stopVoiceTest();
        setTesting(false);
        return;
      }
      await window.miraDesktop.startVoiceTest(draft.voice.microphoneDeviceId || undefined);
      setTesting(true);
      testTimer.current = window.setTimeout(() => {
        testTimer.current = null;
        void window.miraDesktop.stopVoiceTest()
          .catch((error) => setTestError(error instanceof Error ? error.message : String(error)))
          .finally(() => setTesting(false));
      }, 3000);
    } catch (error) {
      setTesting(false);
      setTestError(error instanceof Error ? error.message : String(error));
    }
  }

  if (subsectionId === "input") {
    return (
      <SettingsSectionCard>
        <SettingsToggleField
          label="启用桌宠语音"
          checked={draft.voice.enabled}
          onChange={(checked) => updateDraft((current) => ({ ...current, voice: { ...current.voice, enabled: checked } }))}
        />
        <Field label="全局快捷键">
          <input
            className={cx(inputClass, "bg-white")}
            value={draft.voice.hotkey}
            onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, hotkey: event.target.value } }))}
            placeholder="Ctrl+Space"
          />
        </Field>
        <Field label="麦克风设备">
          <select
            className={cx(inputClass, "bg-white")}
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
  return (
    <SettingsSectionCard>
      <Field label="ASR Provider">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.asrProvider} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrProvider: event.target.value } }))} />
      </Field>
      <Field label="腾讯云 ASR 地址">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.asrBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrBaseUrl: event.target.value } }))} />
      </Field>
      <Field label="ASR 模型">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.asrModel} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrModel: event.target.value } }))} />
      </Field>
      <Field label="腾讯云 SecretId">
        <SettingsSecretInput value={draft.voice.asrSecretId} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrSecretId: value } }))} />
      </Field>
      <Field label="腾讯云 SecretKey">
        <SettingsSecretInput value={draft.voice.asrSecretKey} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrSecretKey: value } }))} />
      </Field>
      <Field label="TTS Provider">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.ttsProvider} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsProvider: event.target.value } }))} />
      </Field>
      <Field label="MiniMax TTS 地址">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.ttsBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsBaseUrl: event.target.value } }))} />
      </Field>
      <Field label="TTS 模型">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.ttsModel} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsModel: event.target.value } }))} />
      </Field>
      <Field label="MiniMax API Key">
        <SettingsSecretInput value={draft.voice.ttsApiKey} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsApiKey: value } }))} />
      </Field>
    </SettingsSectionCard>
  );
}
