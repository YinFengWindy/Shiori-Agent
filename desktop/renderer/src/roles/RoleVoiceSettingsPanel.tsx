import type React from "react";
import { useState } from "react";
import { minimaxVoiceEmotionOptions } from "./roleVoiceConfig";
import type { RoleFormState } from "../shared/types";
import { cx, inputClass } from "../shared/styles";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";

type RoleVoiceSettingsPanelProps = {
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Renders role-owned voice selection, speed, and mood mapping fields. */
export function RoleVoiceSettingsPanel({ bridgeReady, roleForm, onUpdate }: RoleVoiceSettingsPanelProps) {
  const [authorized, setAuthorized] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [previewAudio, setPreviewAudio] = useState("");
  const [error, setError] = useState("");
  const moods = Array.from(new Set([
    ...roleForm.moodCatalog,
    ...Object.keys(roleForm.voiceMoodEmotions),
  ].filter(Boolean)));

  async function cloneVoice(): Promise<void> {
    setError("");
    setCloning(true);
    try {
      const result = await window.miraDesktop.cloneVoice();
      if (result.canceled) return;
      if (!result.ok || !result.voiceId) throw new Error(result.error || "声音复刻失败");
      onUpdate((current) => ({ ...current, voiceEnabled: true, voiceId: result.voiceId || current.voiceId }));
      setPreviewAudio(result.audioBase64 || "");
      if (result.audioBase64) await window.miraDesktop.playVoicePreview(result.audioBase64);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCloning(false);
    }
  }

  async function playPreview(): Promise<void> {
    if (!previewAudio) return;
    try {
      await window.miraDesktop.playVoicePreview(previewAudio);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <div className="grid gap-3 rounded-md border border-[#D8DFE7] bg-white/82 p-4 text-xs text-[#374151]" data-testid="role-voice-config">
      <div className="flex items-center justify-between gap-3">
        <span>角色语音</span>
        <SettingsToggleCard
          checked={roleForm.voiceEnabled}
          ariaLabel="角色语音"
          onChange={(checked) => onUpdate((current) => ({ ...current, voiceEnabled: checked }))}
        />
      </div>
      <label className="grid gap-1.5">
        <span>音色 ID</span>
        <input className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} value={roleForm.voiceId} onChange={(event) => onUpdate((current) => ({ ...current, voiceId: event.target.value }))} placeholder="MiniMax voice_id" />
      </label>
      <label className="grid gap-1.5">
        <span>音色名称</span>
        <input className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} value={roleForm.voiceName} onChange={(event) => onUpdate((current) => ({ ...current, voiceName: event.target.value }))} placeholder="显示名称" />
      </label>
      <label className="grid gap-1.5">
        <span>语速（0.5 - 2.0）</span>
        <input className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} type="number" min="0.5" max="2" step="0.1" value={String(roleForm.voiceSpeed)} onChange={(event) => onUpdate((current) => ({ ...current, voiceSpeed: Number(event.target.value) }))} />
      </label>
      <div className="grid gap-2 border-t border-[#E4EAF0] pt-3">
        <span>声音复刻</span>
        <label className="flex items-start gap-2">
          <input className="mt-0.5 h-4 w-4 rounded border-[#D8DFE7]" type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
          <span>我确认拥有这段录音的使用授权</span>
        </label>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-md border border-[#D8DCE2] px-3 py-2 text-sm transition hover:border-primary disabled:cursor-default disabled:opacity-50" type="button" disabled={!bridgeReady || !authorized || cloning} onClick={() => void cloneVoice()}>{cloning ? "复刻中..." : "选择录音并复刻"}</button>
          <button className="rounded-md border border-[#D8DCE2] px-3 py-2 text-sm transition hover:border-primary disabled:cursor-default disabled:opacity-50" type="button" disabled={!previewAudio || cloning} onClick={() => void playPreview()}>试听</button>
        </div>
        {error ? <div className="text-xs text-[#8f2d2d]">{error}</div> : null}
      </div>
      {moods.map((mood) => (
        <label className="grid gap-1.5" key={mood}>
          <span>{mood} 情绪</span>
          <select className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} value={roleForm.voiceMoodEmotions[mood] ?? ""} onChange={(event) => onUpdate((current) => {
            const next = { ...current.voiceMoodEmotions };
            if (event.target.value) next[mood] = event.target.value;
            else delete next[mood];
            return { ...current, voiceMoodEmotions: next };
          })}>
            <option value="">自动判断</option>
            {minimaxVoiceEmotionOptions.map((emotion) => <option key={emotion} value={emotion}>{emotion}</option>)}
          </select>
        </label>
      ))}
    </div>
  );
}
