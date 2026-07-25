import type React from "react";
import { minimaxVoiceEmotionOptions } from "./roleVoiceConfig";
import type { RoleFormState } from "../shared/types";
import { cx, inputClass } from "../shared/styles";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { RoleVoiceAssetControls } from "./RoleVoiceAssetControls";

type RoleVoiceSettingsPanelProps = {
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Renders role-owned voice selection, speed, and mood mapping fields. */
export function RoleVoiceSettingsPanel({ bridgeReady, roleForm, onUpdate }: RoleVoiceSettingsPanelProps) {
  const moods = Array.from(new Set([
    ...roleForm.moodCatalog,
    ...Object.keys(roleForm.voiceMoodEmotions),
  ].filter(Boolean)));

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
        <span>供应商</span>
        <input className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} value={roleForm.voiceProvider} readOnly={roleForm.voiceOwnership === "shiori_managed"} onChange={(event) => onUpdate((current) => ({ ...current, voiceProvider: event.target.value, voiceOwnership: "external" }))} placeholder="minimax" />
      </label>
      <label className="grid gap-1.5">
        <span>音色 ID</span>
        <input className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} value={roleForm.voiceId} readOnly={roleForm.voiceOwnership === "shiori_managed"} onChange={(event) => onUpdate((current) => ({ ...current, voiceId: event.target.value, voiceOwnership: "external" }))} placeholder="MiniMax voice_id" />
      </label>
      <label className="grid gap-1.5">
        <span>音色名称</span>
        <input className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} value={roleForm.voiceName} onChange={(event) => onUpdate((current) => ({ ...current, voiceName: event.target.value }))} placeholder="显示名称" />
      </label>
      <label className="grid gap-1.5">
        <span>语速（0.5 - 2.0）</span>
        <input className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827]")} type="number" min="0.5" max="2" step="0.1" value={String(roleForm.voiceSpeed)} onChange={(event) => onUpdate((current) => ({ ...current, voiceSpeed: Number(event.target.value) }))} />
      </label>
      <RoleVoiceAssetControls bridgeReady={bridgeReady} roleForm={roleForm} onUpdate={onUpdate} />
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
