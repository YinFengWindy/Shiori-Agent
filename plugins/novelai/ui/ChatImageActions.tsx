import { useRef, useState } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import { errorMessage, cx, ghostButtonClass, type PluginChatImageActionProps, type SessionMessageUpdatePayload } from "@shiori/sdk";
import { novelAiGenerationTimeoutMs } from "./rpcPolicy";

/** Determines whether this image belongs to NovelAI's persisted output collection. */
export function isNovelAiOutput(path: string) {
  return /\/novelai\/outputs\//i.test(path.replaceAll("\\", "/"));
}

/** NovelAI owns the regeneration control, RPC and per-message busy state. */
export function NovelAiChatImageActions({ target, client, onSessionUpdate, onError, onNotice }: PluginChatImageActionProps) {
  const pending = useRef(new Set<string>());
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const key = `${target.sessionKey}:${target.historyKey}`;
  async function regenerate() {
    if (pending.current.has(key)) return;
    pending.current.add(key);
    setBusy(new Set(pending.current));
    onError("");
    try {
      const update = await client.call<SessionMessageUpdatePayload>("regenerateMessageMedia", {
        session_key: target.sessionKey, message_id: target.messageId, media_index: target.mediaIndex,
      }, { timeoutMs: novelAiGenerationTimeoutMs });
      if (update.session?.key !== target.sessionKey || !update.message) throw new Error("重新生成返回了不匹配的会话。");
      onSessionUpdate(target.sessionKey, update);
      onNotice("图片已重新生成。");
    } catch (error) {
      onError(errorMessage(error, { includeDetail: true }));
    } finally {
      pending.current.delete(key);
      setBusy(new Set(pending.current));
    }
  }
  if (!target.sessionKey || !target.messageId || !isNovelAiOutput(target.path)) return null;
  return <button type="button" aria-label="重新生成图片" title="重新生成图片"
    className={cx(ghostButtonClass, "pointer-events-auto grid h-11 w-11 place-items-center rounded-full bg-surface shadow-soft")}
    disabled={busy.has(key)} aria-busy={busy.has(key)} onClick={() => void regenerate()}>
    <ArrowClockwise className="h-5 w-5" weight="bold" />
  </button>;
}
