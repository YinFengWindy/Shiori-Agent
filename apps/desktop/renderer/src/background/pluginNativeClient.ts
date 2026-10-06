import type { PluginNativeApi, PluginNativeContext } from "@yinfengwindy/shiori-sdk";
import type { DesktopApi } from "../../../src/bridge/shared";
import type { BackgroundEffectScope } from "./backgroundEffectScope";

/** Keeps native tokens private to the injected background context and its effect scope. */
export function createPluginNativeClient(api: DesktopApi["native"], context: () => Promise<PluginNativeContext>, scope: BackgroundEffectScope): PluginNativeApi {
  let opened: Promise<string> | undefined;
  let disposed = false;
  const listeners = new Map<string, (phase: "down" | "up") => void>();
  const token = () => {
    scope.ensureActive("native");
    return opened ??= context().then((value) => api.open(value)).catch((error) => { opened = undefined; throw error; });
  };
  const call = async <T,>(method: string, payload: Record<string, unknown> = {}) => {
    const session = await token();
    scope.ensureActive("native");
    return api.call<T>(session, method, payload);
  };
  const unsubscribe = api.onKey((event) => {
    if (!opened || disposed) return;
    void opened.then((session) => { if (!disposed && session === event.token) listeners.get(event.id)?.(event.phase); }, () => undefined);
  });
  scope.addEventEffect("native-key-events", unsubscribe);
  scope.addEffect("native-resources", async () => {
    disposed = true; listeners.clear();
    if (opened) {
      const session = await opened;
      await api.call(session, "close");
    }
  });
  return {
    audio: {
      devices: () => call("audio.devices"),
      startCapture: (deviceId = "") => call("audio.start", { deviceId }),
      stopCapture: () => call("audio.capture.stop"),
      cancelCapture: () => opened ? call("audio.capture.cancel") : Promise.resolve(),
      play: (audio) => call("audio.play", audio),
      stop: () => opened ? call("audio.stop") : Promise.resolve(),
    },
    keys: {
      validate: (accelerator) => call("keys.validate", { accelerator }),
      async register(id, accelerator, listener) { await call("keys.register", { id, accelerator }); listeners.set(id, listener); },
      async unregister(id) { listeners.delete(id); if (opened) await call("keys.unregister", { id }); },
    },
  };
}
