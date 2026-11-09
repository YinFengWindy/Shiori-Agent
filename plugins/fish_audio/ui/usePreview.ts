import { useEffect, useRef, useState } from "react";
import { errorMessage, PluginBridgeError, type PluginHostFeedback, type PluginRpcClient, type TtsResult } from "@yinfengwindy/shiori-sdk";
import type { PreviewState } from "../shared/contracts";

const idle: PreviewState = { id: "", phase: "idle", error: "" };

/** Releases this editor's preview on unmount, reporting unexpected cleanup failures. */
async function release(client: PluginRpcClient, id: string, feedback: PluginHostFeedback) {
  try { await client.background.call("preview.stop", { id }); }
  catch (cause) {
    if (cause instanceof PluginBridgeError && cause.code === "plugin_unavailable" && cause.details?.reason === "context_disposed") return;
    feedback.error("停止 Fish Audio 试听失败", { detail: errorMessage(cause) });
  }
}

/** Retire late synthesis on stop, role switch or editor close. */
export function usePreview(client: PluginRpcClient, roleId: string | null, feedback: PluginHostFeedback) {
  const [state, setState] = useState<PreviewState>(idle);
  const revision = useRef(0);
  const ownedId = useRef<string | null>(null);
  useEffect(() => {
    const retire = () => { revision.current++; };
    retire();
    setState(idle);
    return () => {
      retire();
      const id = ownedId.current;
      ownedId.current = null;
      if (id !== null) void release(client, id, feedback);
    };
  }, [client, roleId, feedback]);
  useEffect(() => {
    if (state.phase !== "playing") return;
    const current = revision.current;
    let active = true;
    const timer = setTimeout(() => {
      void client.background.call<PreviewState>("preview.status").then((next) => {
        if (active && current === revision.current) setState(next.id === ownedId.current ? next : idle);
      }).catch((cause) => {
        if (active && current === revision.current) setState((value) => ({ ...value, phase: "error", error: errorMessage(cause) }));
      });
    }, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [client, state]);

  async function start(text: string) {
    if (!roleId || !text.trim()) return;
    const current = ++revision.current;
    const id = crypto.randomUUID();
    ownedId.current = id;
    setState({ id, phase: "generating", error: "" });
    try {
      const audio = await client.services.call<TtsResult>({ plugin_id: "fish_audio", service_id: "tts" }, "synthesize", { text, role_id: roleId, mood: "" });
      if (current !== revision.current) return;
      const next = await client.background.call<PreviewState>("preview.play", { id, ...audio });
      if (current !== revision.current) { await release(client, id, feedback); return; }
      setState(next);
    } catch (cause) {
      if (current === revision.current) setState({ id, phase: "error", error: errorMessage(cause) });
    }
  }
  async function stop() {
    const current = ++revision.current;
    const id = ownedId.current;
    ownedId.current = null;
    setState(idle);
    if (id === null) return;
    try { await client.background.call("preview.stop", { id }); }
    catch (cause) { if (current === revision.current) setState({ id, phase: "error", error: errorMessage(cause) }); }
  }
  return { state, start, stop, busy: state.phase === "generating" || state.phase === "playing" };
}
