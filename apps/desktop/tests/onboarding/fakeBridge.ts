import type { SettingsSnapshot } from "../../src/bridge/shared";

/** Message every bridge read/write fails with while the fake is offline. */
export const fakeBridgeOfflineMessage = "QA 连接桥不可用";

/**
 * Installs a persistent fake bridge before the renderer loads; state survives page reloads.
 *
 * Runs inside the page (serialized by `addInitScript`), so it must stay self-contained.
 * Payloads mirror what the real Python bridge sends for each method. A method without a
 * handler answers `unknown_method` and is recorded in `state.unknownMethods`, which the
 * test asserts empty: a renderer that starts calling a new method fails the run loudly
 * instead of crashing later on a silently empty payload.
 */
export function installOnboardingFakeBridge(initial: SettingsSnapshot) {
  const stateKey = "qa.onboarding.bridge";
  const offlineMessage = "QA 连接桥不可用";
  const state = JSON.parse(localStorage.getItem(stateKey) ?? "null") ?? {
    settings: initial, roles: [], sessionId: "launch-1", offline: false, failCreate: false, failSave: false, createCalls: 0,
    connectionResult: { ok: true, latency_ms: 180 }, unknownMethods: [],
  };
  const persist = () => localStorage.setItem(stateKey, JSON.stringify(state));
  persist();
  window.addEventListener("qa:bridge", (event) => { Object.assign(state, (event as CustomEvent).detail); persist(); });
  const listeners = new Set<(event: unknown) => void>();
  const role = (fields: Record<string, unknown>) => ({
    id: "qa-role", name: fields.name, description: fields.description, system_prompt: fields.system_prompt,
    runtime_config: {}, channel_bindings: [], avatar: fields.avatar_source ?? null, avatar_abs: fields.avatar_source ?? null,
    chat_background: null, chat_background_abs: null, illustrations: [], illustrations_abs: [],
    asset_categories: [{ id: "default", name: "Default", allow_role_send: false }], asset_category_bindings: {},
    plugin_state: {}, last_message: null,
    created_at: "2026-09-08T00:00:00Z", updated_at: "2026-09-08T00:00:00Z",
  });
  const fail = (code: string, message: string) => ({ code, message });
  const emptyPage = { messages: [], limit: 50, has_more: false, oldest_seq: null, newest_seq: null, total_count: 0, before_seq: null, next_before_seq: null };
  const handlers: Record<string, (payload: Record<string, unknown>) => Record<string, unknown>> = {
    health: () => ({ ok: true }),
    "roles.list": () => ({ roles: state.roles }),
    "roles.create": (payload) => {
      state.createCalls += 1;
      if (state.failCreate) throw fail("qa_failure", "测试头像保存失败");
      const created = role(payload);
      state.roles.push(created);
      if (state.failReadsAfterCreate) state.offline = true;
      return { role: created };
    },
    "roles.tasks.list": () => ({ tasks: [] }),
    "session.openByRole": (payload) => ({
      session: { key: `role:${payload.role_id}`, last_consolidated: 0, messages: [], metadata: { role_id: payload.role_id },
        created_at: "2026-09-08T00:00:00Z", updated_at: "2026-09-08T00:00:00Z" },
      page: emptyPage,
    }),
    "session.imageHistory": (payload) => ({ session_key: payload.session_key, messages: [] }),
    // This fake installs no plugins; the host-owned desktop channel is always listed.
    "plugins.list": () => ({ plugins: [] }),
    "channels.list": () => ({ channels: [{ name: "desktop", label: "桌面端", contact_label: null, chat_types: [],
      plugin_id: null, plugin_enabled: true, state: "active", error: "", status: null }] }),
    "models.test": () => state.connectionResult,
  };
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    applicationSessionId: async () => state.sessionId,
    onEvent: (callback: (event: unknown) => void) => { listeners.add(callback); return () => listeners.delete(callback); },
    windowState: async () => ({ isMaximized: false, isVisible: true }),
    windowControl: async () => undefined,
    bridgeStatus: async () => ({ running: !state.offline, lastError: state.offline ? offlineMessage : null }),
    restartBridge: async () => ({ ok: !state.offline, running: !state.offline, lastError: state.offline ? offlineMessage : null }),
    readSettings: async () => { if (state.offline) throw new Error(offlineMessage); return structuredClone(state.settings); },
    saveSettings: async (formData: SettingsSnapshot["formData"]) => {
      if (state.failSave) return { ok: false, error: fail("qa_failure", "测试模型保存失败") };
      state.settings = { ...state.settings, formData, generation: (state.settings.generation ?? 0) + 1 };
      persist();
      return { ok: true, generation: state.settings.generation, changed: true };
    },
    invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      const respond = (result: Record<string, unknown>, error: { code: string; message: string } | null) => {
        persist();
        return { id: "qa", type: "response", method, payload: result, error };
      };
      if (state.offline) return respond({}, fail("bridge_offline", offlineMessage));
      const handler = handlers[method];
      if (!handler) {
        state.unknownMethods = [...new Set([...state.unknownMethods, method])];
        return respond({}, fail("unknown_method", `unknown method: ${method}`));
      }
      try {
        return respond(handler(payload), null);
      } catch (error) {
        return respond({}, error as { code: string; message: string });
      }
    },
    pickImages: async () => ["qa-avatar"],
    localAssetUrl: () => "/qa-avatar.png",
    reportRendererDiagnostic: () => undefined,
    onVoiceState: () => () => undefined,
  } });
}
