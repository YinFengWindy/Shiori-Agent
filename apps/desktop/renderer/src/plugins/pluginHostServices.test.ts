import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { unavailableLocalAssetUrl } from "../../../src/assets/localAssetContract";
import type { NativeFilePickerOptions } from "../../../src/assets/filePickerContract";
import { toFileUrl } from "../shared/format";
import { pluginHostServicesFor } from "./pluginHostServices";

const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");

/** Installs a stand-in preload bridge for one test. */
function installDesktopApi(miraDesktop: Record<string, unknown>) {
  Object.defineProperty(globalThis, "window", { configurable: true, value: { miraDesktop } });
}

afterEach(() => {
  if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
  else Reflect.deleteProperty(globalThis, "window");
});

test("the host service forwards generic native selection and preserves staging failures", async () => {
  const options: NativeFilePickerOptions = { namespace: "sample", maxFileBytes: 8, filters: [{ name: "Archive", extensions: ["zip"] }] };
  let failed = false;
  const calls: NativeFilePickerOptions[] = [];
  installDesktopApi({
    pickFiles: async (request: NativeFilePickerOptions) => {
      calls.push(request); if (failed) throw new Error("staging failed"); return ["/private/selected.zip"];
    },
  });
  const host = pluginHostServicesFor("sample");
  assert.deepEqual(await host.pickFiles(options), ["/private/selected.zip"]);
  assert.deepEqual(calls, [options]);
  failed = true;
  await assert.rejects(host.pickFiles(options), /staging failed/);
});

test("host.assets.url resolves a path exactly as the host's toFileUrl, placeholder included", () => {
  installDesktopApi({
    localAssetUrl: (path: string) => (path.startsWith("C:/granted/") ? `shiori-asset://local/${encodeURIComponent(path)}` : unavailableLocalAssetUrl),
  });
  const { assets } = pluginHostServicesFor("novelai");
  for (const path of ["C:/granted/avatar.png", "C:/elsewhere/secret.png"]) {
    assert.equal(assets.url(path), toFileUrl(path));
  }
  assert.equal(assets.url("C:/granted/avatar.png"), "shiori-asset://local/C%3A%2Fgranted%2Favatar.png");
  assert.equal(assets.url("C:/elsewhere/secret.png"), unavailableLocalAssetUrl);
});

test("each plugin gets one stable services object whose config reaches only that plugin's table", async () => {
  const requested: Array<{ method: string; pluginId: unknown }> = [];
  installDesktopApi({
    invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      requested.push({ method, pluginId: payload.plugin_id });
      return { id: "1", type: "response", method, error: null, payload: { plugin_id: payload.plugin_id, schema: null, values: { owner: payload.plugin_id }, env_status: {} } };
    },
  });
  assert.equal(pluginHostServicesFor("novelai"), pluginHostServicesFor("novelai"));
  assert.notEqual(pluginHostServicesFor("novelai").config, pluginHostServicesFor("story").config);
  assert.deepEqual(await pluginHostServicesFor("story").config.get(), { owner: "story" });
  assert.deepEqual(requested, [{ method: "plugin.config.get", pluginId: "story" }]);
});
