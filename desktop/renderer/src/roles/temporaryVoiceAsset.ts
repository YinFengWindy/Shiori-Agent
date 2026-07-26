import type { ManagedVoiceAssetReference } from "../shared/types";

/** Abandons one unclaimed provider voice and surfaces bridge failures to the caller. */
export async function abandonTemporaryVoiceAsset(
  asset: ManagedVoiceAssetReference | null | undefined,
): Promise<void> {
  if (!asset) return;
  const response = await window.miraDesktop.invoke({
    method: "voice.clone.abandon",
    payload: {
      provider: asset.provider,
      voice_id: asset.voiceId,
      ownership: asset.ownership,
    },
  });
  if (response.error) throw new Error(response.error.message);
}
