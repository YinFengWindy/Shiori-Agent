import type { ReactNode } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "@shiori/plugin-sdk";

/** Status texts of the memory tab: page availability, the timeline and the document tabs. */
export const memoryStatusText = {
  disconnected: "连接已断开",
  noRole: "请选择角色",
  pluginUnavailable: "记忆插件不可用",
  loading: "加载中…",
  disabled: "语义记忆已停用",
  noItems: "暂无记忆",
  itemMissing: "记忆已不存在",
  documentEmpty: "文档为空",
  documentMissing: "文档缺失",
} as const;

/** The one content frame both memory views render into. */
export function MemoryFrame({ children, label }: { children: ReactNode; label: string }) {
  return <section className="grid min-h-48 content-start gap-4 rounded-md border border-line-soft bg-surface px-5 py-4 text-body text-ink-secondary" aria-label={label}>
    {children}
  </section>;
}

/** A neutral state line inside a memory frame. */
export function MemoryStatusLine({ text }: { text: string }) {
  return <p role="status" className="m-0 text-body-sm text-ink-muted">{text}</p>;
}

/** A failed memory read, worded the same in both views; `onRetry` repeats just that read. */
export function MemoryReadError({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return <InlineError
    message={`读取失败：${error}`}
    actions={onRetry ? <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={onRetry}>重试</button> : undefined}
  />;
}
