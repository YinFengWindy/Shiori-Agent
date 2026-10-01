import type { DesktopBridgeClient } from "./bridge/bridgeClient.js";
import type { SettingsFormData, SettingsSaveOptions } from "./bridge/shared.js";
import { loadSettingsData, saveSettings } from "./settings.js";

type RuntimeBridge = Pick<DesktopBridgeClient, "invoke">;

/** Reads settings and their optimistic concurrency version from one backend snapshot. */
export async function readRuntimeSettings(bridge: RuntimeBridge) {
  const status = await bridge.invoke({ method: "runtime.status", payload: {} });
  if (status.error) throw new Error([status.error.message, status.error.details?.detail].filter(Boolean).join("\n"));
  const { generation, config_toml: content } = status.payload;
  if (typeof generation !== "number" || typeof content !== "string") {
    throw new Error("运行时未返回完整配置快照。");
  }
  return { ...loadSettingsData(content), generation };
}

/** Sends the complete settings transaction without touching the bridge lifecycle. */
export async function applyRuntimeSettings(
  bridge: RuntimeBridge,
  formData: SettingsFormData,
  options?: SettingsSaveOptions,
) {
  return saveSettings(formData, async (payload) => {
    const applied = await bridge.invoke({ method: "runtime.apply", payload });
    if (applied.error) return { ok: false, error: applied.error };
    if (typeof applied.payload.generation !== "number") {
      throw new Error("运行时未返回配置版本。");
    }
    return {
      ok: true,
      generation: applied.payload.generation,
      changed: Boolean(applied.payload.changed),
    };
  }, options);
}
