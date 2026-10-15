import type { ReactNode } from "react";
import type { PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { Composer, type ComposerAction } from "./Composer";
import { InterruptButton } from "./InterruptButton";
import type { AgentCommandResponse } from "./types";

/** Direct input to an agent, recorded as from 「你」; the agent reread follows every attempt. */
export type DirectControl = {
  paneId: string;
  /** Connected, session readable and the agent takes direct input. */
  enabled: boolean;
  /** Rereads the agent so its command record and terminal follow the send. */
  onSent: () => void;
};

/**
 * Direct input as either composer offers it: the action sending the draft to
 * the agent as a prompt (a timeout fails without resending) and the Ctrl+C
 * button beside the send buttons.
 */
export function directControls(client: PluginRpcClient, host: PluginHostServices, { paneId, enabled, onSent }: DirectControl, label: string): { action: ComposerAction; interrupt: ReactNode } {
  return {
    action: {
      label,
      errorTitle: "发送失败",
      disabled: !enabled,
      run: async (text) => {
        try {
          await client.call<AgentCommandResponse>("agents.prompt", { pane_id: paneId, text });
        } finally {
          onSent();
        }
      },
    },
    interrupt: <InterruptButton paneId={paneId} disabled={!enabled} client={client} host={host} onSent={onSent} />,
  };
}

/** Bottom input of an agent without a plugin task: the draft goes straight to the agent; Ctrl+C beside it. */
export function AgentComposer({ direct, client, host }: { direct: DirectControl; client: PluginRpcClient; host: PluginHostServices }) {
  const { action, interrupt } = directControls(client, host, direct, "发送");
  return <Composer label="发给 Agent" primary={action} trailing={interrupt} host={host} />;
}
