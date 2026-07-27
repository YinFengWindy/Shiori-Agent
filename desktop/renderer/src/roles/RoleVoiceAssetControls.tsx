import { Microphone, Play, SpinnerGap, Trash } from "@phosphor-icons/react";
import type React from "react";
import { useState } from "react";
import type { RoleFormState } from "../shared/types";
import { abandonTemporaryVoiceAsset } from "./temporaryVoiceAsset";

type RoleVoiceAssetControlsProps = {
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

const actionButtonClass = "grid h-9 w-9 place-items-center rounded-md border border-[#DDE5EC] bg-white text-[#52606D] transition hover:border-[#AAB7C4] hover:bg-[#F7F9FB] hover:text-[#182230] focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:border-[#E7ECF1] disabled:bg-[#F7F9FB] disabled:text-[#B0BAC5]";

/** Owns provider clone, preview, and managed-asset removal actions. */
export function RoleVoiceAssetControls({ bridgeReady, roleForm, onUpdate }: RoleVoiceAssetControlsProps) {
  const [authorized, setAuthorized] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [previewAudio, setPreviewAudio] = useState("");
  const [error, setError] = useState("");

  async function cloneVoice(): Promise<void> {
    setError("");
    setCloning(true);
    try {
      await abandonTemporaryVoiceAsset(roleForm.temporaryVoiceAsset);
      const result = await window.miraDesktop.cloneVoice();
      if (result.canceled) return;
      if (!result.ok || !result.voiceId || !result.provider || result.ownership !== "shiori_managed") {
        throw new Error(result.error || "声音复刻结果缺少资产归属信息");
      }
      const temporaryVoiceAsset = { provider: result.provider, voiceId: result.voiceId, ownership: "shiori_managed" } as const;
      onUpdate((current) => ({ ...current, voiceEnabled: true, voiceProvider: result.provider || current.voiceProvider, voiceOwnership: "shiori_managed", voiceId: result.voiceId || current.voiceId, pendingVoiceAssetDeletes: [], temporaryVoiceAsset }));
      setPreviewAudio(result.audioBase64 || "");
      if (result.audioBase64) await window.miraDesktop.playVoicePreview(result.audioBase64);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCloning(false);
    }
  }

  async function discardManagedVoice(): Promise<void> {
    try {
      await abandonTemporaryVoiceAsset(roleForm.temporaryVoiceAsset);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      return;
    }
    onUpdate((current) => ({ ...current, voiceOwnership: "external", voiceId: "", voiceName: "", pendingVoiceAssetDeletes: [], temporaryVoiceAsset: null }));
    setPreviewAudio("");
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
    <div className="flex flex-wrap items-center justify-between gap-3" aria-live="polite">
      <label className="flex min-w-0 items-center gap-2 text-xs text-[#667085]">
        <input className="h-4 w-4 rounded border-[#C9D3DD] text-primary focus:ring-2 focus:ring-primary/20" type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
        <span>我确认拥有录音的使用授权</span>
      </label>
      <div className="flex items-center gap-2">
        <button className={actionButtonClass} type="button" disabled={!bridgeReady || !authorized || cloning} onClick={() => void cloneVoice()} aria-label={cloning ? "正在复刻音色" : "选择录音并复刻"} title={cloning ? "正在复刻音色" : "选择录音并复刻"}>
          {cloning ? <SpinnerGap className="h-4 w-4 animate-spin" weight="bold" /> : <Microphone className="h-4 w-4" weight="bold" />}
        </button>
        <button className={actionButtonClass} type="button" disabled={!previewAudio || cloning} onClick={() => void playPreview()} aria-label="试听复刻音色" title="试听复刻音色"><Play className="h-4 w-4" weight="fill" /></button>
        {roleForm.voiceOwnership === "shiori_managed" ? <button className={actionButtonClass} type="button" disabled={cloning} onClick={() => void discardManagedVoice()} aria-label="移除复刻音色" title="移除复刻音色"><Trash className="h-4 w-4 text-[#B54747]" weight="bold" /></button> : null}
      </div>
      {error ? <p className="w-full text-xs text-[#B54747]">{error}</p> : null}
    </div>
  );
}
