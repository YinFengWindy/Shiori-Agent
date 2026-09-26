import { ArrowClockwise } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { ChatMarkdownContent } from "../../chat/ChatMarkdownContent";
import { cx, iconButtonClass } from "../styles";
import type { RoleMemoryDocument } from "../types";

const documentTabs: Array<{ name: RoleMemoryDocument["name"]; label: string }> = [
  { name: "SELF.md", label: "自我" },
  { name: "MEMORY.md", label: "长期" },
  { name: "HISTORY.md", label: "经历" },
  { name: "RECENT_CONTEXT.md", label: "近期" },
  { name: "PENDING.md", label: "待整理" },
];

/** Stateless refresh control used by plugin-owned memory Dashboards. */
export function MemoryRefreshButton({ disabled, onRefresh }: { disabled: boolean; onRefresh: () => void }) {
  return <button className={iconButtonClass} type="button" onClick={onRefresh} disabled={disabled} aria-label="刷新记忆" title="刷新记忆">
    <ArrowClockwise className="h-4 w-4" aria-hidden="true" />
  </button>;
}

/** Stateless document tabs; the plugin owns the current selection. */
export function MemoryDocumentTabs({ selected, onSelect }: { selected: RoleMemoryDocument["name"]; onSelect: (name: RoleMemoryDocument["name"]) => void }) {
  return <div className="flex flex-wrap gap-1 border-b border-line-soft" role="tablist" aria-label="记忆文档">
    {documentTabs.map((item) => (
      <button key={item.name} type="button" role="tab" aria-selected={selected === item.name} onClick={() => onSelect(item.name)} className={cx("min-w-20 border-b-2 px-3 py-2 text-body-sm", selected === item.name ? "border-accent font-medium text-ink" : "border-transparent text-ink-muted hover:text-ink")}>
        {item.label}
      </button>
    ))}
  </div>;
}

type MemoryDocumentPaneProps = {
  name: RoleMemoryDocument["name"];
  document: RoleMemoryDocument | undefined;
  roleId: string;
  bridgeReady: boolean;
  loading: boolean;
  error: string;
  renderError: (message: string) => ReactNode;
};

/** Stateless Markdown pane with distinct loading, empty, missing, and error states. */
export function MemoryDocumentPane({ name, document, roleId, bridgeReady, loading, error, renderError }: MemoryDocumentPaneProps) {
  const failure = roleId && bridgeReady && !loading
    ? error ? `读取失败：${error}` : document?.status === "error" ? `读取失败：${document.error ?? "未知错误"}` : ""
    : "";
  const status = !roleId ? "请选择角色" : !bridgeReady ? "连接已断开" : loading ? "加载中…" : !document || document.status === "missing" ? "文档缺失" : document.status === "empty" ? "文档为空" : "";
  return <div role="tabpanel" className="min-h-48 rounded-md border border-line-soft bg-surface px-5 py-4 text-body text-ink-secondary" data-testid="role-memory-document">
    <p className="mb-3 text-caption font-medium text-ink-muted">{name}</p>
    {failure ? renderError(failure) : status ? <p role="status" className="m-0 text-body-sm text-ink-muted">{status}</p> : <ChatMarkdownContent content={document?.content ?? ""} />}
  </div>;
}
