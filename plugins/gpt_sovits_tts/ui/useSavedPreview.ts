import { useEffect, useState } from "react";
import { usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { RoleVoiceAutosave } from "./useRoleVoice";
import { usePreview } from "./usePreview";

type QueuedPreview = { text: string; mood: string };

/**
 * Preview always plays the stored voice: with an edit still unsaved it first
 * submits the save, then synthesizes once the save completes. A failed save
 * drops the queued preview and blocks previewing until the save succeeds.
 */
export function useSavedPreview(client: PluginRpcClient, roleId: string | null, voice: Pick<RoleVoiceAutosave, "savePhase" | "commit">) {
  const host = usePluginHostServices();
  const preview = usePreview(client, roleId, host.feedback);
  const [text, setText] = useState("你好，今天过得怎么样？");
  const [queued, setQueued] = useState<QueuedPreview | null>(null);
  const saveFailed = voice.savePhase !== "idle" && voice.savePhase !== "saving";
  const { start } = preview;

  // Starts the queued preview once the save it waits for settles; a failure discards it.
  useEffect(() => {
    if (!queued || voice.savePhase === "saving") return;
    setQueued(null);
    if (voice.savePhase === "idle") void start(queued.text, queued.mood);
  }, [queued, voice.savePhase, start]);

  function play(mood: string) {
    if (saveFailed || !text.trim()) return;
    if (voice.savePhase === "idle") { void start(text, mood); return; }
    setQueued({ text, mood });
    voice.commit();
  }

  function stop() {
    setQueued(null);
    void preview.stop();
  }

  return {
    text, setText, play, stop, state: preview.state,
    busy: preview.busy || queued !== null,
    blockedReason: saveFailed ? "保存失败，暂不能试听" : "",
  };
}
