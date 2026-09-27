import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { cx, ghostButtonClass, iconButtonClass, inputClass } from "../styles";
import { Select } from "../ui/Select";
import {
  defaultSemanticStatus, pickOffered, semanticSortOptions, semanticStatusLabels,
  type RoleSemanticFilters, type RoleSemanticItem, type RoleSemanticList, type RoleSemanticQuery,
} from "./roleSemanticMemory";

type SemanticPaneProps = {
  query: RoleSemanticQuery;
  onQuery: (query: RoleSemanticQuery) => void;
  /** Filters the engine declared for this role; null hides every structured filter. */
  filters: RoleSemanticFilters | null;
  list: RoleSemanticList | null;
  loading: boolean;
  error: string;
  selectedId: string;
  onSelect: (id: string) => void;
  detail: RoleSemanticItem | null;
  detailLoading: boolean;
  detailError: string;
  renderError: (message: string) => ReactNode;
};

function metadata(item: RoleSemanticItem) {
  return Object.entries(item).filter(([key, value]) =>
    !["id", "summary", "extra_json", "embedding", "embedding_dim", "content_hash", "has_embedding"].includes(key)
    && value !== null && value !== undefined && value !== "",
  );
}

/** Offers each option as-is, after an "all" choice that clears the filter. */
function valueOptions(values: readonly string[], allLabel: string) {
  return [{ value: "", label: allLabel }, ...values.map((value) => ({ value, label: value }))];
}

type FilterBarProps = {
  query: RoleSemanticQuery;
  filters: RoleSemanticFilters | null;
  onChange: (patch: Partial<RoleSemanticQuery>) => void;
};

/** Search and sort, plus exactly the filter pickers the engine declared. */
function RoleSemanticFilterBar({ query, filters, onChange }: FilterBarProps) {
  const statuses = filters?.status;
  return <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
    <input className={inputClass} aria-label="搜索语义记忆" placeholder="搜索记忆" value={query.q} onChange={(event) => onChange({ q: event.target.value })} />
    {filters?.memory_type && <Select aria-label="记忆类型" value={query.memory_type} options={valueOptions(filters.memory_type, "全部类型")} onValueChange={(memory_type) => onChange({ memory_type })} />}
    {filters?.memory_domain && <Select aria-label="记忆领域" value={query.memory_domain} options={valueOptions(filters.memory_domain, "全部领域")} onValueChange={(memory_domain) => onChange({ memory_domain })} />}
    {statuses && <Select aria-label="记忆状态" value={query.status ?? defaultSemanticStatus} options={statuses.map((value) => ({ value, label: semanticStatusLabels[value] }))} onValueChange={(value) => onChange({ status: pickOffered(statuses, value) })} />}
    <Select aria-label="时间排序" value={query.sort_order} options={semanticSortOptions} onValueChange={(value) => onChange({ sort_order: pickOffered(semanticSortOptions.map((option) => option.value), value) })} />
  </div>;
}

/** Stateless list, filters, pagination, and selected item for a plugin Dashboard. */
export function RoleSemanticMemoryPane({ query, onQuery, filters, list, loading, error, selectedId, onSelect, detail, detailLoading, detailError, renderError }: SemanticPaneProps) {
  const change = (patch: Partial<RoleSemanticQuery>) => onQuery({ ...query, ...patch, page: patch.page ?? 1 });
  const totalPages = Math.max(1, Math.ceil((list?.total ?? 0) / query.page_size));
  return <section className="grid gap-3" aria-label="语义记忆">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="m-0 text-title-sm text-ink">语义记忆</h3>
      {list?.status === "ready" && <span className="text-body-sm text-ink-muted">{list.total} 条</span>}
    </div>
    <RoleSemanticFilterBar query={query} filters={filters} onChange={change} />
    {loading ? <p role="status" className="text-body-sm text-ink-muted">加载中…</p>
      : error ? renderError(`语义记忆读取失败：${error}`)
      : list?.status === "disabled" ? <p role="status" className="text-body-sm text-ink-muted">语义记忆已停用</p>
      : list?.items.length === 0 ? <p role="status" className="text-body-sm text-ink-muted">暂无记忆</p>
      : <div className="divide-y divide-line-soft border-y border-line-soft">
        {list?.items.map((item) => <button key={item.id} type="button" onClick={() => onSelect(item.id)} aria-label={`查看记忆 ${item.id}`} className={cx("flex w-full flex-col gap-1 px-2 py-3 text-left hover:bg-surface-hover", selectedId === item.id && "bg-accent-soft")}>
          <span className="text-body text-ink break-words">{item.summary || item.id}</span>
          <span className="text-caption text-ink-muted break-all">{[item.memory_type, item.memory_domain, item.status, item.happened_at || item.created_at].filter(Boolean).join(" · ")}</span>
        </button>)}
      </div>}
    {list?.status === "ready" && list.total > query.page_size && <nav className="flex items-center justify-end gap-2" aria-label="记忆分页">
      <button type="button" className={iconButtonClass} aria-label="上一页" disabled={query.page <= 1} onClick={() => change({ page: query.page - 1 })}><CaretLeft size={16} /></button>
      <span className="text-body-sm text-ink-muted">{query.page} / {totalPages}</span>
      <button type="button" className={iconButtonClass} aria-label="下一页" disabled={query.page >= totalPages} onClick={() => change({ page: query.page + 1 })}><CaretRight size={16} /></button>
    </nav>}
    {selectedId && <aside className="grid gap-2 border-t border-line-soft pt-3" aria-label="记忆详情">
      <div className="flex items-center justify-between gap-2"><h4 className="m-0 text-body font-medium text-ink">记忆详情</h4><button type="button" className={ghostButtonClass} onClick={() => onSelect("")}>关闭</button></div>
      {detailLoading ? <p role="status">加载中…</p> : detailError ? renderError(`详情读取失败：${detailError}`) : detail && <>
        <p className="m-0 whitespace-pre-wrap break-words text-body text-ink">{detail.summary || detail.id}</p>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-body-sm">
          <dt className="text-ink-muted">ID</dt><dd className="m-0 break-all text-ink-secondary">{detail.id}</dd>
          {metadata(detail).map(([key, value]) => <span className="contents" key={key}><dt className="text-ink-muted">{key}</dt><dd className="m-0 break-all text-ink-secondary">{String(value)}</dd></span>)}
          {detail.extra_json && Object.entries(detail.extra_json).filter(([key]) => key !== "role_id").map(([key, value]) => <span className="contents" key={key}><dt className="text-ink-muted">{key}</dt><dd className="m-0 break-all text-ink-secondary">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></span>)}
        </dl>
      </>}
    </aside>}
  </section>;
}
