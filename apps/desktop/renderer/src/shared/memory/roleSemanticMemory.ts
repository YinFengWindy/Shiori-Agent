/** Item lifecycle filter values; mirrors the backend's `SEMANTIC_STATUS_FILTERS`. */
export type RoleSemanticStatusFilter = "active" | "superseded" | "all";

/** Occurrence-time direction: newest first (`desc`) or oldest first (`asc`). */
export type RoleSemanticSortOrder = "desc" | "asc";

/** Read-only semantic item fields returned by a memory plugin. */
export type RoleSemanticItem = {
  id: string;
  summary: string;
  memory_type?: string;
  memory_domain?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  happened_at?: string;
  source_ref?: string;
  extra_json?: Record<string, unknown>;
  [key: string]: unknown;
};

/**
 * Filter dimensions the engine supports, each listing the values it can apply.
 * Types and domains are the values the current role actually uses; a missing
 * key means the engine cannot filter on that dimension.
 */
export type RoleSemanticFilters = {
  memory_type?: string[];
  memory_domain?: string[];
  status?: RoleSemanticStatusFilter[];
};

/**
 * Server-side search, filter, sort, and page options. Items always sort by
 * occurrence time (record time when missing); empty type/domain and an unset
 * status leave that filter out of the request.
 */
export type RoleSemanticQuery = {
  q: string;
  memory_type: string;
  memory_domain: string;
  status?: RoleSemanticStatusFilter;
  sort_order: RoleSemanticSortOrder;
  page: number;
  page_size: number;
};

/** Role-scoped semantic list response; only a ready engine declares its filters. */
export type RoleSemanticList =
  | {
    role_id: string;
    status: "ready";
    items: RoleSemanticItem[];
    total: number;
    page: number;
    page_size: number;
    filters: RoleSemanticFilters;
  }
  | { role_id: string; status: "disabled"; items: RoleSemanticItem[]; total: number };

/** Role-scoped semantic detail response from one plugin namespace. */
export type RoleSemanticDetail = {
  role_id: string;
  status: "ready" | "disabled";
  item: RoleSemanticItem | null;
};

export const initialSemanticQuery: RoleSemanticQuery = {
  q: "", memory_type: "", memory_domain: "", sort_order: "desc", page: 1, page_size: 20,
};

/** Status an engine applies when the query leaves `status` unset. */
export const defaultSemanticStatus: RoleSemanticStatusFilter = "active";

/** Picker options for the two occurrence-time directions. */
export const semanticSortOptions: readonly { value: RoleSemanticSortOrder; label: string }[] = [
  { value: "desc", label: "最新" },
  { value: "asc", label: "最早" },
];

/** Picker labels for every status an engine may declare. */
export const semanticStatusLabels: Record<RoleSemanticStatusFilter, string> = {
  active: "有效",
  superseded: "已失效",
  all: "全部",
};

/** Narrows a picker's string back to one of the offered values; anything else is a bug. */
export function pickOffered<T extends string>(offered: readonly T[], value: string) {
  const match = offered.find((item) => item === value);
  if (match === undefined) throw new Error(`unexpected option: ${value}`);
  return match;
}

/** List RPC params for one role; unset filters are omitted so engines never receive them. */
export function semanticListParams(roleId: string, query: RoleSemanticQuery) {
  const { memory_type, memory_domain, status, ...rest } = query;
  return {
    role_id: roleId,
    ...rest,
    ...(memory_type ? { memory_type } : {}),
    ...(memory_domain ? { memory_domain } : {}),
    ...(status ? { status } : {}),
  };
}
