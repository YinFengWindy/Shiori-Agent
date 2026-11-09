import { useEffect, useState } from "react";
import { compactGhostButtonClass, errorMessage, Select, SettingsField, SettingsGroup, settingsGroupStackClass, settingsInputClass, SettingsToggleField, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import type { CaptureStatus } from "../capture/contracts";

const phaseLabels: Record<CaptureStatus["phase"], string> = { off: "未开启", paused: "已暂停", starting: "正在开启摄像头", tracking: "跟踪中", no_face: "未检测到人脸", error: "已停止" };
/** Explicit session-only camera controls; enumerating devices never starts capture. */
export function FaceCaptureSettings({ client, host }: PluginSettingsSectionComponentProps) {
  const [status, setStatus] = useState<CaptureStatus | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true, timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try { const next = await client.background.call<CaptureStatus>("capture.status"); if (active) setStatus(next); }
      catch (cause) { if (active) setError(errorMessage(cause)); }
      finally { if (active) timer = setTimeout(() => { void poll(); }, 600); }
    };
    void poll(); return () => { active = false; if (timer) clearTimeout(timer); };
  }, [client]);
  const command = async (name: string, payload: Record<string, unknown> = {}) => {
    setBusy(true); setError("");
    try { setStatus(await client.background.call<CaptureStatus>(name, payload)); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const devices = status?.devices ?? [];
  const options = [{ value: "", label: "默认摄像头" }, ...devices.filter((device) => device.deviceId !== "").map((device) => ({ value: device.deviceId, label: device.label }))];
  if (status?.preferences.deviceId && !options.some((option) => option.value === status.preferences.deviceId)) options.push({ value: status.preferences.deviceId, label: "所选摄像头不可用" });
  return <div className={settingsGroupStackClass}>
    {error || status?.error ? <host.ui.InlineError message={error || status?.error || ""} /> : null}
    <SettingsGroup title="面部捕捉">
      <SettingsToggleField label="摄像头面捕" checked={status?.enabled ?? false} disabled={busy || !status || !status.enabled && !status.available} hint={status && !status.available ? "请先显示 2.5D 形象" : undefined} onChange={(enabled) => { void command(enabled ? "capture.start" : "capture.stop"); }} />
      <SettingsField label="摄像头"><Select aria-label="摄像头" className={settingsInputClass} value={status?.preferences.deviceId ?? ""} options={options} disabled={busy || !status} onValueChange={(deviceId) => { void command("capture.configure", { deviceId }); }} /></SettingsField>
      <SettingsToggleField label="镜像动作" checked={status?.preferences.mirror ?? true} disabled={busy || !status} onChange={(mirror) => { void command("capture.configure", { mirror }); }} />
      <SettingsField label="状态"><span role="status">{status ? phaseLabels[status.phase] : "正在读取…"}</span></SettingsField>
      <SettingsField label="校准"><button type="button" className={compactGhostButtonClass} disabled={busy || status?.phase !== "tracking"} onClick={() => { void command("capture.calibrate"); }}>设为中性姿态</button></SettingsField>
      <button type="button" className={compactGhostButtonClass} disabled={busy || !status?.available} onClick={() => { void command("capture.devices"); }}>刷新摄像头</button>
    </SettingsGroup>
  </div>;
}
