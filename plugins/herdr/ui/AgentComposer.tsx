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

/** Sends the draft to the agent as a prompt; a timeout fails without resending. */
export function directPromptAction(client: PluginRpcClient, { paneId, enabled, onSent }: DirectControl, label: string): ComposerAction {
  return {
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
  };
}

/** Bottom input of an agent without a plugin task: the draft goes straight to the agent; Ctrl+C beside it. */
export function AgentComposer({ direct, client, host }: { direct: DirectControl; client: PluginRpcClient; host: PluginHostServices }) {
  return (
    <Composer
      label="发给 Agent"
      primary={directPromptAction(client, direct, "发送")}
      trailing={<InterruptButton paneId={direct.paneId} disabled={!direct.enabled} client={client} host={host} onSent={direct.onSent} />}
      host={host}
    />
  );
}
