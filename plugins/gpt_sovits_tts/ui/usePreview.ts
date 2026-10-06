import { useEffect, useRef, useState } from "react";
import { errorMessage, type PluginHostFeedback, type PluginRpcClient, type TtsResult } from "@yinfengwindy/shiori-sdk";
import type { PreviewState } from "../shared/contracts";
import { releasePreview } from "./previewCleanup";

const idle: PreviewState = { id: "", role_id: "", phase: "idle", error: "" };

/** The editor owns synthesis lifetime and hands only current results to background playback. */
export function usePreview(client: PluginRpcClient, roleId: string | null, feedback: PluginHostFeedback) {
  const [state, setState] = useState<PreviewState>(idle);
  const revision = useRef(0);
  const ownedId = useRef<string | null>(null);
  useEffect(() => {
    revision.current += 1;
    setState(idle);
    return () => {
      revision.current += 1;
      const id = ownedId.current;
      ownedId.current = null;
      if (id !== null) void releasePreview(client, id, feedback);
    };
  }, [client, roleId, feedback]);
  useEffect(() => {
    if (state.phase !== "playing" || !state.id) return;
    const current = revision.current;
    let active = true;
    const timer = setTimeout(() => {
      void client.background.call<PreviewState>("preview.status").then((next) => {
        if (active && current === revision.current) setState(next.id === ownedId.current ? next : idle);
      }).catch((cause) => {
        if (active && current === revision.current) setState((value) => ({ ...value, phase: "error", error: errorMessage(cause) }));
      });
    }, 500);
    return () => { active = false; clearTimeout(timer); };
  }, [client, state]);
  async function start(text: string, mood: string) {
    if (!roleId) return;
    const current = ++revision.current;
    const id = crypto.randomUUID();
    ownedId.current = id;
    setState({ id, role_id: roleId, phase: "generating", error: "" });
    try {
      const audio = await client.services.call<TtsResult>({ plugin_id: "gpt_sovits_tts", service_id: "tts" }, "synthesize", { role_id: roleId, text, mood });
      if (current !== revision.current) return;
      const next = await client.background.call<PreviewState>("preview.play", { id, role_id: roleId, ...audio });
      if (current !== revision.current) { await releasePreview(client, next.id, feedback); return; }
      ownedId.current = next.id;
      setState(next);
    } catch (cause) {
      if (current === revision.current) setState({ id, role_id: roleId, phase: "error", error: errorMessage(cause) });
    }
  }
  async function stop() {
    // Manual stop owns a mounted editor and reports failures inline, unlike release.
    const current = ++revision.current;
    setState(idle);
    const id = ownedId.current;
    ownedId.current = null;
    if (id === null) return;
    try { await client.background.call("preview.stop", { id }); }
    catch (cause) { if (current === revision.current) setState({ ...idle, phase: "error", error: errorMessage(cause) }); }
  }
  return { state, start, stop, busy: state.phase === "generating" || state.phase === "playing" };
}
