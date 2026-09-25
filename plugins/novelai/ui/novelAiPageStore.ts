import type { PluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { useSyncExternalStore } from "react";
import { errorMessage } from "../../../apps/desktop/renderer/src/shared/feedback/feedbackStore";
import type { PluginHostFeedback } from "../../../apps/desktop/renderer/src/plugins/pluginHostFeedback";
import type { RoleRecord } from "../../../apps/desktop/renderer/src/shared/types";
import type { GenerationFailure, NovelAiReadiness } from "./generationFailure";
import type { ImageGenerateResult, ImageHistoryRecord, ImageStudioFormState } from "./types";

export type NovelAiView = "studio" | "prompt-tags";

/** Which part of the prompt-tag workspace is open. */
export type PromptTagWorkspaceSectionId = "list" | "create" | "detail";

export type NovelAiPageState = {
  view: NovelAiView;
  promptTagSection: PromptTagWorkspaceSectionId;
  roles: RoleRecord[];
  /** Whether `roles` reflects a real fetch yet, vs. the initial empty placeholder. */
  rolesLoaded: boolean;
  /** The generation form; kept here so a prompt survives switching to the tag library and back. */
  form: ImageStudioFormState;
  /** Token readiness from `plugin.novelai.status`; null until known (treated as usable). */
  readiness: NovelAiReadiness | null;
  submitting: boolean;
  history: ImageHistoryRecord[];
  selectedRecordId: string;
  latestResult: ImageGenerateResult | null;
  /** Why the last generation failed, shown in the canvas until dismissed or superseded. */
  failure: GenerationFailure | null;
  /** The record the last successful generation produced; it plays the reveal motion once. */
  revealRecordId: string;
};

export const initialStudioForm: ImageStudioFormState = {
  roleId: "",
  prompt: "",
  negativePrompt: "",
  mode: "txt2img",
  baseImagePath: "",
  strength: 0.7,
  noise: 0.2,
  sizePreset: "square",
  customWidth: "",
  customHeight: "",
  model: "nai-diffusion-4-5-curated",
};

// This plugin's `nav.page` entry has two mount points that render as
// siblings under the host's `DesktopAppFrame` (the page in `<main>`, its
// Sidebar in the host's resizable track — see issue #226 gap A/B). They are
// not a React context away from each other (the host owns everything in
// between), so state both of them read — which view is open, which
// prompt-tag section, the role roster used by the nav-rail
// `selectBlockedReason` guard — has to live outside either component. A
// module-level store notified via `useSyncExternalStore` is the smallest
// thing that works for two components the host may mount/unmount
// independently, without asking the host to plumb cross-slot state.
//
// The generation form lives here too (restyle #362 stage 7 moved it from the
// sidebar into the page): the page swaps between the studio and the tag
// library, and a half-written prompt must not be lost on that round trip.
function initialState(): NovelAiPageState {
  return {
    view: "studio",
    promptTagSection: "list",
    roles: [],
    rolesLoaded: false,
    form: initialStudioForm,
    readiness: null,
    submitting: false,
    history: [],
    selectedRecordId: "",
    latestResult: null,
    failure: null,
    revealRecordId: "",
  };
}

let state: NovelAiPageState = initialState();
const listeners = new Set<() => void>();

/** Current snapshot, for the sibling action modules of this store. */
export function getNovelAiState(): NovelAiPageState {
  return state;
}

/** Publishes a new snapshot; callers return early instead when nothing changed. */
export function commitNovelAiState(next: NovelAiPageState): void {
  state = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Subscribes a component to every field of the shared novelai page state. */
export function useNovelAiPageStore(): NovelAiPageState {
  return useSyncExternalStore(subscribe, getNovelAiState, getNovelAiState);
}

export function setView(view: NovelAiView): void {
  if (state.view === view) return;
  commitNovelAiState({ ...state, view });
}

export function openPromptTagLibrary(): void {
  if (state.view === "prompt-tags" && state.promptTagSection === "list") return;
  commitNovelAiState({ ...state, view: "prompt-tags", promptTagSection: "list" });
}

export function backToStudio(): void {
  setView("studio");
}

export function setPromptTagSection(section: PromptTagWorkspaceSectionId): void {
  if (state.promptTagSection === section) return;
  commitNovelAiState({ ...state, promptTagSection: section });
}

/** Used by the library page, which can also navigate back to "list" while the studio view is showing. */
export function openPromptTagWorkspaceSection(section: PromptTagWorkspaceSectionId): void {
  if (section === "list") setView("prompt-tags");
  setPromptTagSection(section);
}

/**
 * Applies a partial form edit. Switching the generation role also drops the
 * previous role's failure and fresh result: they describe someone else's
 * canvas.
 */
export function updateStudioForm(patch: Partial<ImageStudioFormState>): void {
  const changed = (Object.keys(patch) as Array<keyof ImageStudioFormState>)
    .some((key) => patch[key] !== state.form[key]);
  if (!changed) return;
  const form = { ...state.form, ...patch };
  const roleChanged = form.roleId !== state.form.roleId;
  commitNovelAiState({
    ...state,
    form,
    ...(roleChanged ? { failure: null, latestResult: null, revealRecordId: "" } : {}),
  });
}

export function selectRecord(recordId: string): void {
  if (state.selectedRecordId === recordId && !state.failure) return;
  commitNovelAiState({ ...state, selectedRecordId: recordId, failure: null });
}

/** Dismisses the canvas failure (or drops it once the attempt that caused it is abandoned). */
export function clearFailure(): void {
  if (!state.failure) return;
  commitNovelAiState({ ...state, failure: null });
}

/** Surfaces a failed host request (roster loading) at the plugin page boundary, fronted by 吟风. */
export function reportPageError(report: PluginHostFeedback, error: unknown): void {
  report.error("生图页面加载失败", { detail: errorMessage(error), persona: true });
}

let rolesInflight: Promise<void> | null = null;

/** Fetches roles through injected host services, sharing concurrent requests across sidebar and page. */
export async function refreshRoles(host: PluginHostServices): Promise<void> {
  if (rolesInflight) return rolesInflight;
  rolesInflight = (async () => {
    try {
      const roles = await host.listRoles();
      commitNovelAiState({ ...state, roles, rolesLoaded: true });
    } finally {
      rolesInflight = null;
    }
  })();
  return rolesInflight;
}

/**
 * The exact string the pre-migration `useNavigationHistory.openImageStudio`
 * used for this same check — kept verbatim (owner decision: 拦住 + 给提示);
 * the host shows it as a warning toast.
 */
const ZERO_ROLES_BLOCKED_REASON = "请先创建至少一个角色，再进入生图。";

/**
 * Synchronous nav-rail guard (issue #226 gap B): refuses to navigate into
 * this page while zero roles exist. `selectBlockedReason` must return
 * synchronously, so before the roster has ever loaded this fails *open*
 * (returns `null`) — the in-page empty state (`NovelAIPage`) is the safety
 * net for exactly that race.
 */
export function selectBlockedReasonForNovelAiPage(host: PluginHostServices): string | null {
  void refreshRoles(host).catch((error: unknown) => reportPageError(host.feedback, error));
  if (!state.rolesLoaded || state.roles.length > 0) return null;
  return ZERO_ROLES_BLOCKED_REASON;
}

/** Test-only: resets every module-level field (optionally seeding some) so each test starts clean. */
export function resetNovelAiPageStoreForTests(seed: Partial<NovelAiPageState> = {}): void {
  state = { ...initialState(), ...seed };
  rolesInflight = null;
}
