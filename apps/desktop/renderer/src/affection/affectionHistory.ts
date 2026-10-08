import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** Where one affection change came from; mirrors the backend's `AffectionSource`. */
export type AffectionSource = "init" | "turn" | "decay";

/** One affection history entry; the `init` entry has no previous value or delta. */
export type AffectionHistoryEntry = {
  time: string;
  before: number | null;
  after: number;
  delta: number | null;
  reason: string;
  source: AffectionSource;
};

/**
 * One newest-first page of `roles.affection.history`, 1-based like the memory
 * timeline. `affection` is the current summary, null until initialized.
 */
export type AffectionHistoryPage = {
  role_id: string;
  affection: AffectionSummary | null;
  items: AffectionHistoryEntry[];
  total: number;
  page: number;
  page_size: number;
};

/** Entries per "load more" batch. */
export const affectionHistoryBatchSize = 20;

/** Reads one page of the role's affection history; another role's answer is an error. */
export async function readAffectionHistory(invoke: DesktopInvoke, roleId: string, page: number) {
  const response = await invokeBridgePayload<AffectionHistoryPage>(invoke, "roles.affection.history", {
    role_id: roleId,
    page,
    page_size: affectionHistoryBatchSize,
  });
  if (response.role_id !== roleId) throw new Error("角色不匹配");
  return response;
}
