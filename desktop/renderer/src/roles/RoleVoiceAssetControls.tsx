import type React from "react";
import { useEffect, useRef, useState } from "react";
import { DeleteIcon } from "../shared/icons";
import type { RoleFormState } from "../shared/types";

type TemporaryVoiceAsset = {
  provider: string;
  voiceId: string;
  ownership: "shiori_managed";
};

type RoleVoiceAssetControlsProps = {
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Owns provider clone, preview, and managed-asset removal actions. */
export function RoleVoiceAssetControls({ bridgeReady, roleForm, onUpdate }: RoleVoiceAssetControlsProps) {
  const [authorized, setAuthorized] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [previewAudio, setPreviewAudio] = useState("");
  const [error, setError] = useState("");
  const temporaryAssetRef = useRef<TemporaryVoiceAsset | null>(null);

  useEffect(() => () => {
    void abandonTemporaryVoice(temporaryAssetRef.current);
  }, []);

  async function cloneVoice(): Promise<void> {
    setError("");
    setCloning(true);
    try {
      await abandonTemporaryVoice(temporaryAssetRef.current);
      temporaryAssetRef.current = null;
      const result = await window.miraDesktop.cloneVoice();
      if (result.canceled) return;
      if (!result.ok || !result.voiceId || !result.provider || result.ownership !== "shiori_managed") {
        throw new Error(result.error || "声音复刻结果缺少资产归属信息");
      }
      temporaryAssetRef.current = {
        provider: result.provider,
        voiceId: result.voiceId,
        ownership: "shiori_managed",
      };
      onUpdate((current) => ({
        ...current,
        voiceEnabled: true,
        voiceProvider: result.provider || current.voiceProvider,
        voiceOwnership: "shiori_managed",
        voiceId: result.voiceId || current.voiceId,
        pendingVoiceAssetDeletes: [],
      }));
      setPreviewAudio(result.audioBase64 || "");
      if (result.audioBase64) await window.miraDesktop.playVoicePreview(result.audioBase64);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCloning(false);
    }
  }

  function discardManagedVoice(): void {
    void abandonTemporaryVoice(temporaryAssetRef.current);
    temporaryAssetRef.current = null;
    onUpdate((current) => ({
      ...current,
      voiceOwnership: "external",
      voiceId: "",
      voiceName: "",
      pendingVoiceAssetDeletes: [],
    }));
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
    <div className="grid gap-2 border-t border-[#E4EAF0] pt-3">
      <span>声音复刻</span>
      <label className="flex items-start gap-2">
        <input className="mt-0.5 h-4 w-4 rounded border-[#D8DFE7]" type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
        <span>我确认拥有这段录音的使用授权</span>
      </label>
      <div className="flex flex-wrap gap-2">
        <button className="rounded-md border border-[#D8DCE2] px-3 py-2 text-sm transition hover:border-primary disabled:cursor-default disabled:opacity-50" type="button" disabled={!bridgeReady || !authorized || cloning} onClick={() => void cloneVoice()}>{cloning ? "复刻中..." : "选择录音并复刻"}</button>
        <button className="rounded-md border border-[#D8DCE2] px-3 py-2 text-sm transition hover:border-primary disabled:cursor-default disabled:opacity-50" type="button" disabled={!previewAudio || cloning} onClick={() => void playPreview()}>试听</button>
        {roleForm.voiceOwnership === "shiori_managed" ? (
          <button className="inline-flex items-center gap-1.5 rounded-md border border-[#D8DCE2] px-3 py-2 text-sm text-[#8f2d2d] transition hover:border-[#8f2d2d] disabled:cursor-default disabled:opacity-50" type="button" disabled={cloning} onClick={discardManagedVoice} title="移除复刻音色">
            <DeleteIcon />
            移除
          </button>
        ) : null}
      </div>
      {error ? <div className="text-xs text-[#8f2d2d]">{error}</div> : null}
    </div>
  );
}

async function abandonTemporaryVoice(asset: TemporaryVoiceAsset | null): Promise<void> {
  if (!asset) return;
  await window.miraDesktop.invoke({
    method: "voice.clone.abandon",
    payload: {
      provider: asset.provider,
      voice_id: asset.voiceId,
      ownership: asset.ownership,
    },
  });
}
