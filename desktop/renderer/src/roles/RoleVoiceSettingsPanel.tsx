import { CaretDown, PencilSimple, Waveform } from "@phosphor-icons/react";
import type React from "react";
import { useState } from "react";
import { minimaxVoiceEmotionOptions } from "./roleVoiceConfig";
import type { RoleFormState } from "../shared/types";
import { cx } from "../shared/styles";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { RoleVoiceAssetControls } from "./RoleVoiceAssetControls";

type RoleVoiceSettingsPanelProps = {
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

const voiceFieldClass = "w-full border-0 border-b border-[#DDE5EC] bg-[#F7F9FB] px-3 py-2.5 text-sm text-[#182230] transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 placeholder:text-[#98A2B3]";

/** Renders role-owned voice selection, speed, and mood mapping fields. */
export function RoleVoiceSettingsPanel({ bridgeReady, roleForm, onUpdate }: RoleVoiceSettingsPanelProps) {
  const [technicalFieldsOpen, setTechnicalFieldsOpen] = useState(false);
  const moods = Array.from(new Set([
    ...roleForm.moodCatalog,
    ...Object.keys(roleForm.voiceMoodEmotions),
  ].filter(Boolean)));
  const voiceName = roleForm.voiceName.trim() || "尚未选择音色";
  const voiceSource = roleForm.voiceOwnership === "shiori_managed" ? "Shiori 管理音色" : `${roleForm.voiceProvider || "MiniMax"} 外部音色`;

  return (
    <section aria-labelledby="role-voice-heading" className="grid gap-5" data-testid="role-voice-config">
      <div className="flex items-start justify-between gap-4 border-b border-[#E7ECF1] pb-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[#EFF6F4] text-[#2E7D5B]" aria-hidden="true">
            <Waveform className="h-5 w-5" weight="duotone" />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-[#182230]" id="role-voice-heading">当前音色</h2>
            <p className="mt-1 truncate text-sm text-[#475467]">{voiceName}</p>
            <p className="mt-0.5 text-xs text-[#7B8794]">{voiceSource}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className={roleForm.voiceEnabled ? "text-xs text-[#2E7D5B]" : "text-xs text-[#7B8794]"}>{roleForm.voiceEnabled ? "已启用" : "未启用"}</span>
          <SettingsToggleCard checked={roleForm.voiceEnabled} ariaLabel="角色语音" onChange={(checked) => onUpdate((current) => ({ ...current, voiceEnabled: checked }))} />
        </div>
      </div>

      <RoleVoiceAssetControls bridgeReady={bridgeReady} roleForm={roleForm} onUpdate={onUpdate} />

      <div className="border-t border-[#E7ECF1] pt-1">
        <button className="flex w-full items-center justify-between py-3 text-left text-xs font-medium text-[#52606D] transition hover:text-[#182230] focus:outline-none focus:ring-2 focus:ring-primary/20" type="button" aria-expanded={technicalFieldsOpen} onClick={() => setTechnicalFieldsOpen((current) => !current)}>
          <span className="inline-flex items-center gap-1.5"><PencilSimple className="h-4 w-4" weight="bold" />编辑音色参数</span>
          <CaretDown className={cx("h-4 w-4 transition-transform", technicalFieldsOpen && "rotate-180")} weight="bold" />
        </button>
        {technicalFieldsOpen ? (
          <div className="grid gap-4 border-t border-[#EEF2F5] py-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-xs text-[#667085]"><span>音色名称</span><input className={voiceFieldClass} value={roleForm.voiceName} onChange={(event) => onUpdate((current) => ({ ...current, voiceName: event.target.value }))} placeholder="显示名称" /></label>
            <label className="grid gap-1.5 text-xs text-[#667085]"><span>语速（0.5 - 2.0）</span><input className={voiceFieldClass} type="number" min="0.5" max="2" step="0.1" value={String(roleForm.voiceSpeed)} onChange={(event) => onUpdate((current) => ({ ...current, voiceSpeed: Number(event.target.value) }))} /></label>
            <label className="grid gap-1.5 text-xs text-[#667085]"><span>Provider</span><input className={voiceFieldClass} value={roleForm.voiceProvider} readOnly={roleForm.voiceOwnership === "shiori_managed"} onChange={(event) => onUpdate((current) => ({ ...current, voiceProvider: event.target.value, voiceOwnership: "external" }))} placeholder="minimax" /></label>
            <label className="grid gap-1.5 text-xs text-[#667085]"><span>音色 ID</span><input className={voiceFieldClass} value={roleForm.voiceId} readOnly={roleForm.voiceOwnership === "shiori_managed"} onChange={(event) => onUpdate((current) => ({ ...current, voiceId: event.target.value, voiceOwnership: "external" }))} placeholder="MiniMax voice_id" /></label>
          </div>
        ) : null}
      </div>

      {moods.length > 0 ? (
        <div className="grid gap-3 border-t border-[#E7ECF1] pt-5">
          <div><h3 className="text-sm font-medium text-[#182230]">情绪映射</h3><p className="mt-1 text-xs text-[#7B8794]">为角色状态选择优先使用的语音情绪。</p></div>
          <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {moods.map((mood) => (
              <label className="grid grid-cols-[minmax(0,1fr)_132px] items-center gap-3 border-b border-[#EEF2F5] py-2.5 text-sm" key={mood}>
                <span className="truncate text-[#475467]">{mood}</span>
                <select className="rounded-md border-0 bg-[#F7F9FB] px-2.5 py-2 text-xs text-[#344054] transition focus:outline-none focus:ring-2 focus:ring-primary/20" value={roleForm.voiceMoodEmotions[mood] ?? ""} onChange={(event) => onUpdate((current) => {
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
        </div>
      ) : null}
    </section>
  );
}
