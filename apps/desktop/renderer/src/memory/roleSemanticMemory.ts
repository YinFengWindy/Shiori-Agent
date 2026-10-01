import type { SelectOption } from "@shiori/sdk";

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
  happened_at?: string | null;
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
 * Server-side search, filter, and sort options. Items always sort by
 * occurrence time (record time when missing); empty type/domain and an unset
 * status leave that filter out of the request.
 */
export type RoleSemanticQuery = {
  q: string;
  memory_type: string;
  memory_domain: string;
  status?: RoleSemanticStatusFilter;
  sort_order: RoleSemanticSortOrder;
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

/** A fresh timeline's query: no search or filters (engine default status), newest first. */
export const initialSemanticQuery: RoleSemanticQuery = {
  q: "", memory_type: "", memory_domain: "", sort_order: "desc",
};

/** Items per "load more" batch. */
export const semanticBatchSize = 20;

/** Status an engine applies when the query leaves `status` unset. */
export const defaultSemanticStatus: RoleSemanticStatusFilter = "active";

/** The two occurrence-time directions, in picker order. */
export const semanticSortOrders: readonly RoleSemanticSortOrder[] = ["desc", "asc"];

/** Picker labels for each occurrence-time direction. */
export const semanticSortLabels: Record<RoleSemanticSortOrder, string> = {
  desc: "最新",
  asc: "最早",
};

/** Shared-picker options for the two occurrence-time directions. */
export const semanticSortOptions: readonly SelectOption[] = semanticSortOrders.map((value) => ({ value, label: semanticSortLabels[value] }));

/** Every status filter value, in picker order. */
export const semanticStatusFilters: readonly RoleSemanticStatusFilter[] = ["active", "superseded", "all"];

/** Picker labels for every status an engine may declare. */
export const semanticStatusLabels: Record<RoleSemanticStatusFilter, string> = {
  active: "有效",
  superseded: "已失效",
  all: "全部",
};

/** Label of an item's status; a status outside the known set shows as-is. */
export function semanticStatusLabel(value: string) {
  const status = semanticStatusFilters.find((item) => item === value);
  return status ? semanticStatusLabels[status] : value;
}

/** Narrows a picker's string back to one of the offered values; anything else is a bug. */
export function pickOffered<T extends string>(offered: readonly T[], value: string) {
  const match = offered.find((item) => item === value);
  if (match === undefined) throw new Error(`unexpected option: ${value}`);
  return match;
}

/** Whether two queries ask the engine for the same items. */
export function sameSemanticQuery(left: RoleSemanticQuery, right: RoleSemanticQuery) {
  return left.q === right.q && left.memory_type === right.memory_type && left.memory_domain === right.memory_domain
    && left.status === right.status && left.sort_order === right.sort_order;
}

function sameValues(left: readonly string[] | undefined, right: readonly string[] | undefined) {
  return left === right || (left !== undefined && right !== undefined && left.length === right.length && left.every((value, index) => value === right[index]));
}

/** Whether two engine declarations offer the same filter dimensions and values. */
export function sameSemanticFilters(left: RoleSemanticFilters | null, right: RoleSemanticFilters | null) {
  if (left === null || right === null) return left === right;
  return sameValues(left.memory_type, right.memory_type) && sameValues(left.memory_domain, right.memory_domain) && sameValues(left.status, right.status);
}

/** List RPC params for one role's batch; unset filters are omitted so engines never receive them. */
export function semanticListParams(roleId: string, query: RoleSemanticQuery, page: number) {
  const { memory_type, memory_domain, status, ...rest } = query;
  return {
    role_id: roleId,
    ...rest,
    page,
    page_size: semanticBatchSize,
    ...(memory_type ? { memory_type } : {}),
    ...(memory_domain ? { memory_domain } : {}),
    ...(status ? { status } : {}),
  };
}
