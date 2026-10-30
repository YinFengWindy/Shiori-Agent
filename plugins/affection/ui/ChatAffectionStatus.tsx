import type { PluginChatAffectionComponentProps } from "@yinfengwindy/shiori-sdk";
import { ChatAffectionMeter } from "./ChatAffectionMeter";
import { StatusMeter } from "./StatusMeter";
import { useAffectionChatStatus } from "./useAffectionChatStatus";

/**
 * The plugin's part of the chat status sidebar: relationship tags, the
 * affection meter and loneliness, all read through the plugin's own RPC.
 * The host keys it by role.
 */
export function ChatAffectionStatus({ roleId, client, host }: PluginChatAffectionComponentProps) {
  const { status, error } = useAffectionChatStatus(client, host, roleId);
  if (error && !status) return <host.ui.InlineError message={error} />;
  if (!status) return null;
  const loneliness = Math.max(0, Math.min(100, Number.isFinite(status.loneliness) ? status.loneliness : 0));
  return <div className="grid gap-3" data-testid="chat-affection-status">
    {status.relation_tags.length ? (
      <div className="flex flex-wrap gap-1">
        {status.relation_tags.map((tag) => (
          <span key={tag} className="rounded-full bg-accent-soft px-1.5 py-0.5 text-caption text-accent-text">{tag}</span>
        ))}
      </div>
    ) : (
      <div className="text-caption text-ink-muted">关系标签还在生成中</div>
    )}
    {status.affection ? <ChatAffectionMeter summary={status.affection} /> : null}
    <StatusMeter label="寂寞值" value={Math.round(loneliness)} percent={loneliness} heightClass="h-1.5" />
  </div>;
}
