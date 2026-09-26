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

/** Server-side search, filter, time sort, and page options. */
export type RoleSemanticQuery = {
  q: string;
  memory_type: string;
  memory_domain: string;
  status: string;
  sort_by: "created_at" | "updated_at" | "happened_at";
  sort_order: "asc" | "desc";
  page: number;
  page_size: number;
};

/** Role-scoped semantic list response from one plugin namespace. */
export type RoleSemanticList = {
  role_id: string;
  status: "ready" | "disabled";
  items: RoleSemanticItem[];
  total: number;
  page?: number;
  page_size?: number;
};

/** Role-scoped semantic detail response from one plugin namespace. */
export type RoleSemanticDetail = {
  role_id: string;
  status: "ready" | "disabled";
  item: RoleSemanticItem | null;
};

export const initialSemanticQuery: RoleSemanticQuery = {
  q: "", memory_type: "", memory_domain: "", status: "active",
  sort_by: "created_at", sort_order: "desc", page: 1, page_size: 20,
};
