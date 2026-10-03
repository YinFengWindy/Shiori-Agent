import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { BridgeError, PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { describeGenerationFailure } from "./generationFailure";
import { initialStudioForm, resetNovelAiPageStoreForTests } from "./novelAiPageStore";
import { reportGenerationFailure, useImageStudio } from "./useImageStudio";

afterEach(() => {
  resetNovelAiPageStoreForTests();
});

const networkFailure = describeGenerationFailure(new BridgeError("连接超时", "novelai_network"));

describe("reportGenerationFailure", () => {
  it("fronts the toast with the failure's scene, and only her face while the card already says it", () => {
    const fake = createFakeHostServices();
    reportGenerationFailure(fake.host.feedback, networkFailure);
    reportGenerationFailure(fake.host.feedback, { ...networkFailure, title: "连不上 NovelAI（第二次）" }, { cardOnScreen: true });
    const [alone, withCard] = fake.feedback;
    assert.equal(alone?.options?.persona, "network");
    assert.equal(alone?.options?.personaQuiet, false);
    assert.equal(withCard?.options?.persona, "network");
    assert.equal(withCard?.options?.personaQuiet, true);
  });
});

describe("useImageStudio submit", () => {
  /** Mounts the studio hook with a generate call that fails once `fail()` is called. */
  async function mountStudio() {
    const fake = createFakeHostServices();
    let fail!: () => void;
    const generate = new Promise<never>((_resolve, reject) => { fail = () => reject(new BridgeError("连接超时", "novelai_network")); });
    const client = createFakePluginClient({
      call: async <T,>(method: string) => (method === "generate" ? generate : ({ records: [], configured: true, reason: "", message: "" } as T)),
    });
    resetNovelAiPageStoreForTests({ rolesLoaded: true, roles: [], form: { ...initialStudioForm, roleId: "rin", prompt: "1girl" } });
    let submit!: () => Promise<void>;
    function Probe() {
      submit = useImageStudio(client, "rin").submit;
      return null;
    }
    const view = await mountTestComponent(<PluginHostServicesProvider services={fake.host}><Probe /></PluginHostServicesProvider>);
    return { view, fake, fail, submit: () => submit() };
  }

  it("keeps the toast quiet while the studio shows the failure card", async () => {
    const { view, fake, fail, submit } = await mountStudio();
    try {
      let pending!: Promise<void>;
      await act(async () => { pending = submit(); });
      await act(async () => { fail(); await pending; });
      const toast = fake.feedback.at(-1);
      assert.equal(toast?.options?.persona, "network");
      assert.equal(toast?.options?.personaQuiet, true);
    } finally { await view.cleanup(); }
  });

  it("lets her say the line when the studio was left before the failure came back", async () => {
    const { view, fake, fail, submit } = await mountStudio();
    let pending!: Promise<void>;
    await act(async () => { pending = submit(); });
    await view.cleanup();
    fail();
    await pending;
    const toast = fake.feedback.at(-1);
    assert.equal(toast?.options?.persona, "network");
    assert.equal(toast?.options?.personaQuiet, false);
  });
});
