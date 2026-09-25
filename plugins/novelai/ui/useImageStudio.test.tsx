import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { createPluginRpcClient, type PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { pluginHostFeedback } from "../../../apps/desktop/renderer/src/plugins/pluginHostFeedback";
import { PluginHostServicesProvider } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { BridgeError } from "../../../apps/desktop/renderer/src/shared/bridgeInvoke";
import { getFeedbackSnapshot, resetFeedback } from "../../../apps/desktop/renderer/src/shared/feedback/feedbackStore";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { describeGenerationFailure } from "./generationFailure";
import { initialStudioForm, resetNovelAiPageStoreForTests } from "./novelAiPageStore";
import { reportGenerationFailure, useImageStudio } from "./useImageStudio";

afterEach(() => {
  resetFeedback();
  resetNovelAiPageStoreForTests();
});

const networkFailure = describeGenerationFailure(new BridgeError("连接超时", "novelai_network"));

describe("reportGenerationFailure", () => {
  it("fronts the toast with the failure's scene, and only her face while the card already says it", () => {
    reportGenerationFailure(pluginHostFeedback, networkFailure);
    reportGenerationFailure(pluginHostFeedback, { ...networkFailure, title: "连不上 NovelAI（第二次）" }, { cardOnScreen: true });
    const [alone, withCard] = getFeedbackSnapshot();
    assert.equal(alone?.persona, "network");
    assert.equal(alone?.personaQuiet, undefined);
    assert.equal(withCard?.persona, "network");
    assert.equal(withCard?.personaQuiet, true);
  });
});

describe("useImageStudio submit", () => {
  /** Mounts the studio hook with a generate call that fails once `fail()` is called. */
  async function mountStudio() {
    const view = await mountTestComponent(null);
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: {
        onEvent: () => () => undefined,
        invoke: async ({ method }: { method: string }) => ({ id: "x", type: "response", method, error: null, payload: method === "plugin.config.get" ? { schema: {}, values: {} } : {} }),
      },
    });
    let fail!: () => void;
    const generate = new Promise<never>((_resolve, reject) => { fail = () => reject(new BridgeError("连接超时", "novelai_network")); });
    const client: PluginRpcClient = {
      ...createPluginRpcClient("novelai"),
      call: async <T,>(method: string) => (method === "generate" ? generate : ({ records: [], configured: true, reason: "", message: "" } as T)),
    };
    resetNovelAiPageStoreForTests({ rolesLoaded: true, roles: [], form: { ...initialStudioForm, roleId: "rin", prompt: "1girl" } });
    let submit!: () => Promise<void>;
    function Probe() {
      submit = useImageStudio(client, "rin").submit;
      return null;
    }
    await view.render(<PluginHostServicesProvider services={desktopPluginHostServices}><Probe /></PluginHostServicesProvider>);
    return { view, fail, submit: () => submit() };
  }

  it("keeps the toast quiet while the studio shows the failure card", async () => {
    const { view, fail, submit } = await mountStudio();
    try {
      let pending!: Promise<void>;
      await act(async () => { pending = submit(); });
      await act(async () => { fail(); await pending; });
      const toast = getFeedbackSnapshot().at(-1);
      assert.equal(toast?.persona, "network");
      assert.equal(toast?.personaQuiet, true);
    } finally { await view.cleanup(); }
  });

  it("lets her say the line when the studio was left before the failure came back", async () => {
    const { view, fail, submit } = await mountStudio();
    let pending!: Promise<void>;
    await act(async () => { pending = submit(); });
    await view.cleanup();
    fail();
    await pending;
    const toast = getFeedbackSnapshot().at(-1);
    assert.equal(toast?.persona, "network");
    assert.equal(toast?.personaQuiet, undefined);
  });
});
