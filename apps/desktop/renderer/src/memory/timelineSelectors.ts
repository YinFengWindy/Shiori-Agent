import { formatDate, formatTimestamp, parseTimestamp } from "../shared/format";
import { semanticStatusLabel, type RoleSemanticItem, type RoleSemanticList } from "./roleSemanticMemory";

/** Neutral placeholder for an item without summary text. */
export const emptySummaryLabel = "无摘要";

/** Occurrence time of an item, falling back to when it was recorded. */
export function itemOccurredAt(item: RoleSemanticItem) {
  return item.happened_at || item.created_at || "";
}

/** Whether an item has been replaced by a newer statement. */
export function isSuperseded(item: RoleSemanticItem) {
  return item.status === "superseded";
}

/** One date heading and its items, in list order. */
export type TimelineGroup = { key: string; label: string; items: RoleSemanticItem[] };

function localDateKey(value: string) {
  const date = parseTimestamp(value);
  return date ? `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}` : "";
}

/**
 * Groups items by the local calendar date of their occurrence time, keeping
 * the engine's order. Consecutive items without a readable time share a
 * "时间未知" group.
 */
export function groupTimeline(items: readonly RoleSemanticItem[]): TimelineGroup[] {
  const groups: TimelineGroup[] = [];
  for (const item of items) {
    const occurredAt = itemOccurredAt(item);
    const key = localDateKey(occurredAt);
    const last = groups.at(-1);
    if (last?.key === key) last.items.push(item);
    else groups.push({ key, label: key ? formatDate(occurredAt) : "时间未知", items: [item] });
  }
  return groups;
}

/** The loaded timeline: every batch so far, and whether asking for another is pointless. */
export type TimelineBatches = { list: RoleSemanticList; exhausted: boolean };

/**
 * The end is reached when a batch comes back short, adds nothing new, or the
 * loaded items cover the engine's total. Offset paging can still skip or
 * repeat items when memories change between batches; that is an accepted
 * limitation (repeats are dropped by id, refresh starts over).
 */
function batchesFrom(list: RoleSemanticList, returned: number, fresh: number): TimelineBatches {
  const exhausted = list.status !== "ready" || fresh === 0 || returned < list.page_size || list.items.length >= list.total;
  return { list, exhausted };
}

/** The first batch of a scope. */
export function firstTimelineBatch(list: RoleSemanticList) {
  return batchesFrom(list, list.items.length, list.items.length);
}

/** Appends the next batch, dropping items an earlier batch already showed. */
export function appendTimelineBatch(previous: TimelineBatches, next: TimelineBatches) {
  const { list: before } = previous;
  const { list: batch } = next;
  if (before.status !== "ready" || batch.status !== "ready") return next;
  const seen = new Set(before.items.map((item) => item.id));
  const fresh = batch.items.filter((item) => !seen.has(item.id));
  return batchesFrom({ ...batch, items: [...before.items, ...fresh] }, batch.items.length, fresh.length);
}

const fieldLabels: Record<string, string> = {
  memory_type: "类型",
  status: "状态",
  memory_domain: "领域",
  source_ref: "来源",
  happened_at: "发生时间",
  created_at: "记录时间",
  updated_at: "更新时间",
  reinforcement: "强化次数",
  emotional_weight: "情感权重",
  scope_channel: "渠道",
  scope_chat_id: "会话",
  role_id: "角色",
  session_key: "会话键",
  turn_seq: "轮次",
  strength: "强度",
  resource: "资源",
  recall_count: "召回次数",
  emb_count: "向量数",
};

const timeFields = new Set(["happened_at", "created_at", "updated_at"]);
/** Shown elsewhere (summary) or not meaningful to readers (the item key). */
const omittedFields = new Set(["id", "summary", "extra_json"]);

function displayValue(key: string, value: unknown) {
  if (timeFields.has(key) && typeof value === "string") return formatTimestamp(value) || value;
  if (key === "status" && typeof value === "string") return semanticStatusLabel(value);
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/**
 * Detail rows of one item: known fields first with Chinese labels and
 * localized times, then any other field (including `extra_json`) under its
 * own name. Empty values and fields already listed are skipped.
 */
export function memoryDetailRows(item: RoleSemanticItem) {
  const entries = [...Object.entries(item), ...Object.entries(item.extra_json ?? {})]
    .filter(([key, value]) => !omittedFields.has(key) && value !== null && value !== undefined && value !== "");
  const isKnown = (key: string) => Object.hasOwn(fieldLabels, key);
  const ordered = [
    ...Object.keys(fieldLabels).flatMap((key) => entries.filter(([name]) => name === key)),
    ...entries.filter(([name]) => !isKnown(name)),
  ];
  const seen = new Set<string>();
  return ordered.flatMap(([key, value]) => {
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ key, label: isKnown(key) ? fieldLabels[key] : key, value: displayValue(key, value) }];
  });
}
