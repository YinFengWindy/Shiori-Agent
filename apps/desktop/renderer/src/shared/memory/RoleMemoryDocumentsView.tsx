import { ArrowClockwise } from "@phosphor-icons/react";
import { useState } from "react";
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

type Props = {
  roleId: string;
  bridgeReady: boolean;
  documents: RoleMemoryDocument[];
  loading: boolean;
  error: string;
  onRefresh: () => void;
};

/** Shared read-only presentation for a memory plugin's Markdown documents. */
export function RoleMemoryDocumentsView({ roleId, bridgeReady, documents, loading, error, onRefresh }: Props) {
  const [selected, setSelected] = useState<RoleMemoryDocument["name"]>("SELF.md");
  const document = documents.find((item) => item.name === selected);
  const status = !roleId ? "请选择角色" : !bridgeReady ? "连接已断开" : loading ? "加载中…" : error ? `读取失败：${error}` : !document || document.status === "missing" ? "文档缺失" : document.status === "empty" ? "文档为空" : document.status === "error" ? `读取失败：${document.error ?? "未知错误"}` : "";

  return (
    <section className="grid gap-5" aria-label="角色记忆" data-testid="role-memory-panel">
      <div className="flex items-center justify-between gap-3">
        <h2 className="m-0 text-title-sm text-ink">Markdown 记忆</h2>
        <button className={iconButtonClass} type="button" onClick={onRefresh} disabled={!roleId || !bridgeReady} aria-label="刷新记忆" title="刷新记忆">
          <ArrowClockwise className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="flex flex-wrap gap-1 border-b border-line-soft" role="tablist" aria-label="记忆文档">
        {documentTabs.map((item) => (
          <button key={item.name} type="button" role="tab" aria-selected={selected === item.name} onClick={() => setSelected(item.name)} className={cx("min-w-20 border-b-2 px-3 py-2 text-body-sm", selected === item.name ? "border-accent font-medium text-ink" : "border-transparent text-ink-muted hover:text-ink")}>
            {item.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="min-h-48 rounded-md border border-line-soft bg-surface px-5 py-4 text-body text-ink-secondary" data-testid="role-memory-document">
        <p className="mb-3 text-caption font-medium text-ink-muted">{selected}</p>
        {status ? <p role="status" className="m-0 text-body-sm text-ink-muted">{status}</p> : <ChatMarkdownContent content={document?.content ?? ""} />}
      </div>
    </section>
  );
}
