import { formatDate, parseTimestamp } from "./format";

/** One local-date heading and its items, in list order. */
export type LocalDateGroup<T> = { key: string; label: string; items: T[] };

/** Label of the group whose items have no readable time. */
export const unknownDateLabel = "时间未知";

/** The local calendar date of a bridge timestamp as a grouping key; "" when unreadable. */
export function localDateKey(value: string) {
  const date = parseTimestamp(value);
  return date ? `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}` : "";
}

/**
 * Groups consecutive items by the local calendar date of `timeOf(item)`,
 * keeping list order (memory timeline, affection history). Consecutive items
 * without a readable time share a 「时间未知」 group.
 */
export function groupByLocalDate<T>(items: readonly T[], timeOf: (item: T) => string): LocalDateGroup<T>[] {
  const groups: LocalDateGroup<T>[] = [];
  for (const item of items) {
    const time = timeOf(item);
    const key = localDateKey(time);
    const last = groups.at(-1);
    if (last?.key === key) last.items.push(item);
    else groups.push({ key, label: key ? formatDate(time) : unknownDateLabel, items: [item] });
  }
  return groups;
}
