import { errorMessage, feedback } from "../../../apps/desktop/renderer/src/shared/feedback/feedbackStore";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { describeGenerationFailure, type GenerationFailure, type NovelAiReadiness } from "./generationFailure";
import { commitNovelAiState, getNovelAiState } from "./novelAiPageStore";
import { novelAiGenerationTimeoutMs } from "./rpcPolicy";
import type { ImageGenerateResult, ImageHistoryRecord } from "./types";

/** How many recent records the filmstrip keeps for one role. */
const historyLimit = 24;

/** Loads one role's recent generations; keeps the selection when it is still present. */
export async function loadHistory(client: PluginRpcClient, roleId: string): Promise<void> {
  try {
    const payload = await client.call<{ records: ImageHistoryRecord[] }>("history", {
      role_id: roleId,
      limit: historyLimit,
    });
    const records = Array.isArray(payload.records) ? payload.records : [];
    const state = getNovelAiState();
    const selectedRecordId = records.some((record) => record.id === state.selectedRecordId)
      ? state.selectedRecordId
      : (records[0]?.id ?? "");
    commitNovelAiState({ ...state, history: records, selectedRecordId });
  } catch (loadError) {
    feedback.error("生图历史加载失败", { detail: errorMessage(loadError) });
  }
}

/**
 * Asks the backend whether a usable token is configured, so an unset token
 * (empty, or an unexpanded `${ENV}`) reads as 「未配置」 before anyone
 * presses 生成. A failed status call leaves readiness unknown rather than
 * blocking generation on a probe.
 */
export async function refreshReadiness(client: PluginRpcClient): Promise<void> {
  let readiness: NovelAiReadiness | null;
  try {
    readiness = await client.call<NovelAiReadiness>("status", {});
  } catch {
    readiness = null;
  }
  const state = getNovelAiState();
  if (sameReadiness(state.readiness, readiness)) return;
  commitNovelAiState({ ...state, readiness });
}

function sameReadiness(a: NovelAiReadiness | null, b: NovelAiReadiness | null): boolean {
  if (!a || !b) return a === b;
  return a.configured === b.configured && a.reason === b.reason && a.message === b.message;
}

/**
 * Submits a request already resolved by the form (model/mode/role), then
 * refreshes that role's history. Resolves to the failure (also kept in the
 * store for the canvas) so the caller can raise its toast, or null.
 */
export async function submitGenerate(
  client: PluginRpcClient,
  payload: Record<string, unknown>,
): Promise<GenerationFailure | null> {
  commitNovelAiState({ ...getNovelAiState(), submitting: true, failure: null });
  let result: ImageGenerateResult;
  try {
    const response = await client.call<{ result: ImageGenerateResult }>("generate", payload, {
      timeoutMs: novelAiGenerationTimeoutMs,
    });
    result = response.result;
  } catch (submitError) {
    const failure = describeGenerationFailure(submitError);
    const state = getNovelAiState();
    commitNovelAiState({
      ...state,
      submitting: false,
      failure,
      // The backend just proved the token unusable; reflect that everywhere.
      readiness: failure.kind === "not-configured"
        ? { configured: false, reason: state.readiness?.reason || "missing", message: failure.message }
        : state.readiness,
    });
    return failure;
  }
  commitNovelAiState({
    ...getNovelAiState(),
    submitting: false,
    latestResult: result,
    revealRecordId: result.record_id,
    selectedRecordId: result.record_id,
  });
  await loadHistory(client, String(payload.role_id ?? ""));
  return null;
}
