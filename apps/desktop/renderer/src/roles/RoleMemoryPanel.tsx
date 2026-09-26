import { ArrowClockwise } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { ChatMarkdownContent } from "../chat/ChatMarkdownContent";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { cx } from "../shared/styles";
import type { RoleMemoryDocument, RoleMemoryDocumentsPayload } from "../shared/types";
import { rolePanelGhostButtonClass } from "./roleEditorStyles";

const documents: Array<{ name: RoleMemoryDocument["name"]; label: string }> = [
  { name: "SELF.md", label: "自我" },
  { name: "MEMORY.md", label: "长期" },
  { name: "HISTORY.md", label: "经历" },
  { name: "RECENT_CONTEXT.md", label: "近期" },
  { name: "PENDING.md", label: "待整理" },
];

type LoadedDocuments = {
  roleId: string;
  documents: RoleMemoryDocument[];
  error: string;
  loading: boolean;
};

/** Reads and displays the five Markdown documents owned by the selected role. */
export function RoleMemoryPanel({ roleId, bridgeReady }: { roleId: string; bridgeReady: boolean }) {
  const [selected, setSelected] = useState<RoleMemoryDocument["name"]>("SELF.md");
  const [refresh, setRefresh] = useState(0);
  const [loaded, setLoaded] = useState<LoadedDocuments | null>(null);

  useEffect(() => {
    if (!roleId || !bridgeReady) return;
    let cancelled = false;
    setLoaded({ roleId, documents: [], error: "", loading: true });
    void invokeBridgePayload<RoleMemoryDocumentsPayload>(
      window.miraDesktop.invoke,
      "roles.memory.documents",
      { role_id: roleId },
    ).then((response) => {
      if (!cancelled && response.role_id === roleId) {
        setLoaded({ roleId, documents: response.documents, error: "", loading: false });
      }
    }).catch((error: unknown) => {
      if (!cancelled) {
        setLoaded({ roleId, documents: [], error: error instanceof Error ? error.message : String(error), loading: false });
      }
    });
    return () => { cancelled = true; };
  }, [roleId, bridgeReady, refresh]);

  const current = loaded?.roleId === roleId ? loaded : null;
  const document = current?.documents.find((item) => item.name === selected);
  const status = !roleId ? "请选择角色" : !bridgeReady ? "连接已断开" : !current || current.loading ? "加载中…" : current.error ? `读取失败：${current.error}` : !document ? "文档缺失" : document.status === "missing" ? "文档缺失" : document.status === "empty" ? "文档为空" : document.status === "error" ? `读取失败：${document.error ?? "未知错误"}` : "";

  return (
    <section className="grid gap-5" aria-label="角色记忆" data-testid="role-memory-panel">
      <div className="flex items-center justify-between gap-3">
        <h2 className="m-0 text-title-sm text-ink">Markdown 记忆</h2>
        <button className={rolePanelGhostButtonClass} type="button" onClick={() => setRefresh((value) => value + 1)} disabled={!roleId || !bridgeReady} aria-label="刷新记忆" title="刷新记忆">
          <ArrowClockwise className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="flex flex-wrap gap-1 border-b border-line-soft" role="tablist" aria-label="记忆文档">
        {documents.map((item) => (
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
