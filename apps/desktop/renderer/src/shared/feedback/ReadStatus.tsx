import type { ReactNode } from "react";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "@yinfengwindy/shiori-sdk";
import { InlineError } from "./InlineError";

/** Status texts shared by read-only role views (memory, affection). */
export const readStatusText = {
  disconnected: "连接已断开",
  noRole: "请选择角色",
  loading: "加载中…",
} as const;

/** The content frame a read-only view renders into. */
export function ReadFrame({ children, label }: { children: ReactNode; label: string }) {
  return <section className="grid min-h-48 content-start gap-4 rounded-md border border-line-soft bg-surface px-5 py-4 text-body text-ink-secondary" aria-label={label}>
    {children}
  </section>;
}

/** A neutral state line inside a read-only view. */
export function ReadStatusLine({ text }: { text: string }) {
  return <p role="status" className="m-0 text-body-sm text-ink-muted">{text}</p>;
}

/** A failed read, worded the same everywhere; `onRetry` repeats just that read. */
export function ReadError({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return <InlineError
    message={`读取失败：${error}`}
    actions={onRetry ? <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={onRetry}>重试</button> : undefined}
  />;
}
