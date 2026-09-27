import type { ReactNode } from "react";
import { InlineError } from "../shared/feedback/InlineError";

/** Status texts shared by the timeline and the document tabs. */
export const memoryStatusText = {
  loading: "加载中…",
  disabled: "语义记忆已停用",
  noItems: "暂无记忆",
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

/** A failed memory read, worded the same in both views. */
export function MemoryReadError({ error }: { error: string }) {
  return <InlineError message={`读取失败：${error}`} />;
}
