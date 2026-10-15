import { useRef, useState } from "react";
import { StopCircle } from "@phosphor-icons/react";
import { errorMessage, iconButtonClass, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { AgentCommandResponse } from "./types";

/**
 * Presses Ctrl+C in the agent once per click, without confirmation; a
 * failure is reported through the host's feedback.
 */
export function InterruptButton({ paneId, disabled, client, host, onSent }: {
  paneId: string;
  disabled: boolean;
  client: PluginRpcClient;
  host: PluginHostServices;
  /** Called after the keys were recorded, sent or not, so the view can reread. */
  onSent: () => void;
}) {
  const [pending, setPending] = useState(false);
  // A second Ctrl+C would quit some agents; never send one before the first settled.
  const inFlight = useRef(false);
  const interrupt = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    try {
      await client.call<AgentCommandResponse>("agents.keys", { pane_id: paneId, keys: ["ctrl+c"] });
    } catch (reason) {
      host.feedback.error("中断未发送", { detail: errorMessage(reason) });
    } finally {
      inFlight.current = false;
      setPending(false);
      onSent();
    }
  };
  return (
    <button type="button" className={iconButtonClass} aria-label="中断" title="中断（Ctrl+C）" disabled={disabled || pending} onClick={() => { void interrupt(); }}>
      <StopCircle className="h-4 w-4" aria-hidden="true" />
    </button>
  );
}
