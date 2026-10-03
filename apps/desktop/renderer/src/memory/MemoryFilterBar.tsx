import { inputClass, Select, type SelectOption } from "@yinfengwindy/shiori-sdk";
import {
  defaultSemanticStatus, pickOffered, semanticSortOptions, semanticSortOrders, semanticStatusLabels,
  type RoleSemanticFilters, type RoleSemanticQuery,
} from "./roleSemanticMemory";

type MemoryFilterBarProps = {
  query: RoleSemanticQuery;
  /** Filters the engine declared for this role; null shows only search and sort. */
  filters: RoleSemanticFilters | null;
  onChange: (patch: Partial<RoleSemanticQuery>) => void;
};

/** Offers each value as-is, after an "all" choice that clears the filter. */
function valueOptions(values: readonly string[], allLabel: string): SelectOption[] {
  return [{ value: "", label: allLabel }, ...values.map((value) => ({ value, label: value }))];
}

/** Search and sort, plus exactly the filter pickers the engine declared. */
export function MemoryFilterBar({ query, filters, onChange }: MemoryFilterBarProps) {
  const statuses = filters?.status;
  return <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
    <input className={inputClass} aria-label="搜索记忆" placeholder="搜索" value={query.q} onChange={(event) => onChange({ q: event.target.value })} />
    {filters?.memory_type && <Select aria-label="记忆类型" value={query.memory_type} options={valueOptions(filters.memory_type, "全部类型")} onValueChange={(memory_type) => onChange({ memory_type })} />}
    {filters?.memory_domain && <Select aria-label="记忆领域" value={query.memory_domain} options={valueOptions(filters.memory_domain, "全部领域")} onValueChange={(memory_domain) => onChange({ memory_domain })} />}
    {statuses && <Select aria-label="记忆状态" value={query.status ?? defaultSemanticStatus} options={statuses.map((value): SelectOption => ({ value, label: semanticStatusLabels[value] }))} onValueChange={(value) => onChange({ status: pickOffered(statuses, value) })} />}
    <Select aria-label="时间排序" value={query.sort_order} options={semanticSortOptions} onValueChange={(value) => onChange({ sort_order: pickOffered(semanticSortOrders, value) })} />
  </div>;
}
