import { Select } from "../shared/ui/Select";
import { CaretDown, Waveform } from "@phosphor-icons/react";
import type React from "react";
import { useState } from "react";
import { minimaxVoiceEmotionOptions } from "./roleVoiceConfig";
import type { RoleFormState } from "../shared/types";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { cx } from "../shared/styles";
import { roleFieldClass as voiceFieldClass, roleFieldLabelClass, rolePanelGhostButtonClass } from "./roleEditorStyles";
import { RoleCapabilityCard } from "./RoleCapabilityCard";
import { roleVoiceStatus } from "./roleCapabilityStatus";

type RoleVoiceSettingsPanelProps = {
  roleForm: RoleFormState;
  /** Global voice output (see `globalVoiceOutputEnabled`); null while unknown. */
  globalVoiceEnabled?: boolean | null;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Renders role-owned voice selection, speed, and mood mapping fields as one capability card. */
export function RoleVoiceSettingsPanel({ roleForm, globalVoiceEnabled = null, onUpdate }: RoleVoiceSettingsPanelProps) {
  const [technicalFieldsOpen, setTechnicalFieldsOpen] = useState(false);
  const moods = Array.from(new Set([
    ...roleForm.moodCatalog,
    ...Object.keys(roleForm.voiceMoodEmotions),
  ].filter(Boolean)));
  const voiceName = roleForm.voiceName.trim() || "尚未选择音色";
  const voiceSource = roleForm.voiceOwnership === "shiori_managed" ? "Shiori 管理音色" : `${roleForm.voiceProvider || "MiniMax"} 外部音色`;
  const status = roleVoiceStatus({ roleEnabled: roleForm.voiceEnabled, voiceId: roleForm.voiceId, globalEnabled: globalVoiceEnabled });

  return (
    <RoleCapabilityCard
      icon={<Waveform className="h-5 w-5" weight="duotone" />}
      title="语音"
      status={status}
      data-testid="role-voice-config"
      control={<SettingsToggleCard checked={roleForm.voiceEnabled} ariaLabel="角色语音" onChange={(checked) => onUpdate((current) => ({ ...current, voiceEnabled: checked }))} />}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-4">
        <div className="grid min-w-0 gap-0.5">
          <span className="text-caption text-ink-muted">当前音色</span>
          <span className="truncate text-body text-ink">{voiceName}</span>
          <span className="text-caption text-ink-muted">{voiceSource}</span>
        </div>
        <button className={rolePanelGhostButtonClass} type="button" aria-expanded={technicalFieldsOpen} onClick={() => setTechnicalFieldsOpen((current) => !current)}>
          编辑参数
          <CaretDown className={cx("h-3.5 w-3.5 transition-transform duration-quick", technicalFieldsOpen && "rotate-180")} weight="bold" aria-hidden="true" />
        </button>
      </div>

      {technicalFieldsOpen ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <label className={roleFieldLabelClass}><span>音色名称</span><input className={voiceFieldClass} value={roleForm.voiceName} onChange={(event) => onUpdate((current) => ({ ...current, voiceName: event.target.value }))} placeholder="显示名称" /></label>
          <label className={roleFieldLabelClass}><span>语速（0.5 - 2.0）</span><input className={voiceFieldClass} type="number" min="0.5" max="2" step="0.1" value={String(roleForm.voiceSpeed)} onChange={(event) => onUpdate((current) => ({ ...current, voiceSpeed: Number(event.target.value) }))} /></label>
          <label className={roleFieldLabelClass}><span>服务商</span><input className={voiceFieldClass} value={roleForm.voiceProvider} readOnly={roleForm.voiceOwnership === "shiori_managed"} onChange={(event) => onUpdate((current) => ({ ...current, voiceProvider: event.target.value, voiceOwnership: "external" }))} placeholder="minimax" /></label>
          <label className={roleFieldLabelClass}><span>音色 ID</span><input className={voiceFieldClass} value={roleForm.voiceId} readOnly={roleForm.voiceOwnership === "shiori_managed"} onChange={(event) => onUpdate((current) => ({ ...current, voiceId: event.target.value, voiceOwnership: "external" }))} placeholder="MiniMax voice_id" /></label>
        </div>
      ) : null}

      {moods.length > 0 ? (
        <div className="grid gap-2 border-t border-line-soft pt-4">
          <h3 className="m-0 text-body-sm font-medium text-ink">情绪映射</h3>
          <div className="grid gap-x-6 sm:grid-cols-2">
            {moods.map((mood) => (
              <label className="grid grid-cols-[minmax(0,1fr)_148px] items-center gap-3 border-b border-line-soft py-2 text-body last:border-b-0" key={mood}>
                <span className="truncate text-ink-secondary">{mood}</span>
                <Select aria-label={mood} className={voiceFieldClass} value={roleForm.voiceMoodEmotions[mood] ?? ""} onValueChange={(value) => onUpdate((current) => {
                  const next = { ...current.voiceMoodEmotions };
                  if (value) next[mood] = value;
                  else delete next[mood];
                  return { ...current, voiceMoodEmotions: next };
                })} options={[{ value: "", label: "自动判断" }, ...minimaxVoiceEmotionOptions.map((emotion) => ({ value: emotion, label: emotion }))]} />
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </RoleCapabilityCard>
  );
}
