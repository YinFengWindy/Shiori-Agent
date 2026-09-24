import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type React from "react";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { ImageStage } from "./ImageStage";
import type { StageView } from "./studioSelectors";

const notConfigured = { kind: "not-configured", title: "NovelAI 未配置", message: "NovelAI token 引用的环境变量 NOVELAI_TOKEN 未设置", opensSettings: true } as const;

/** Mounts inside a DOM whose bridge can turn file paths into asset URLs. */
async function mountStage(element: React.ReactElement) {
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { localAssetUrl: (path: string) => `asset://${path}` } });
  await view.render(element);
  return view;
}

function buttonByText(container: HTMLElement, text: string): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((element) => element.textContent?.trim() === text);
}

describe("ImageStage", () => {
  it("shows a token failure with its cause and a way to the plugin's settings", async () => {
    let opened = 0;
    let dismissed = 0;
    const view = await mountStage(<ImageStage view={{ kind: "failure", failure: notConfigured }}
      onOpenSettings={() => { opened += 1; }} onDismissFailure={() => { dismissed += 1; }} onReusePrompt={() => undefined} />);
    try {
      const card = view.container.querySelector('[data-testid="novelai-stage-failure"]');
      assert.match(card?.textContent ?? "", /NovelAI 未配置/);
      assert.match(card?.textContent ?? "", /NOVELAI_TOKEN/);
      await act(async () => buttonByText(view.container, "去设置")?.click());
      assert.equal(opened, 1);
      await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="关闭"]')?.click());
      assert.equal(dismissed, 1);
    } finally { await view.cleanup(); }
  });

  it("a failure settings cannot fix offers only dismissal", async () => {
    const view = await mountStage(<ImageStage view={{ kind: "failure", failure: { kind: "network", title: "连不上 NovelAI", message: "", opensSettings: false } }}
      onOpenSettings={() => undefined} onDismissFailure={() => undefined} onReusePrompt={() => undefined} />);
    try {
      assert.equal(buttonByText(view.container, "去设置"), undefined);
      assert.ok(buttonByText(view.container, "知道了"));
    } finally { await view.cleanup(); }
  });

  it("shows the picture with its size and seed, plays the reveal only when fresh, and reuses its prompt", async () => {
    const record = {
      id: "r", created_at: "", role_id: "rin", session_key: "", mode: "txt2img" as const, prompt: "1girl", negative_prompt: "lowres", model: "m",
      sampler: "", steps: 28, seed: 42, width: 832, height: 1216, base_image_path: "", output_paths: ["D:/out/r.png"], wrote_back_to_role: false, role_asset_paths: [],
    };
    const reused: string[] = [];
    const image = (reveal: boolean): StageView => ({ kind: "image", path: "D:/out/r.png", record, reveal, notice: null });
    const view = await mountStage(<ImageStage view={image(true)} onReusePrompt={(item) => reused.push(item.prompt)} />);
    try {
      assert.ok(view.container.querySelector("img.nai-reveal"));
      assert.match(view.container.textContent ?? "", /832 × 1216/);
      assert.match(view.container.textContent ?? "", /种子 42/);
      await act(async () => buttonByText(view.container, "复用提示词")?.click());
      assert.deepEqual(reused, ["1girl"]);
      await view.render(<ImageStage view={image(false)} onReusePrompt={() => undefined} />);
      assert.equal(view.container.querySelector("img.nai-reveal"), null);
    } finally { await view.cleanup(); }
  });

  it("keeps history browsable under a standing not-configured notice", async () => {
    const view = await mountStage(<ImageStage view={{ kind: "image", path: "D:/out/r.png", record: null, reveal: false, notice: notConfigured }}
      onOpenSettings={() => undefined} onReusePrompt={() => undefined} />);
    try {
      assert.ok(view.container.querySelector("img"));
      assert.match(view.container.querySelector('[role="status"]')?.textContent ?? "", /NovelAI 未配置/);
    } finally { await view.cleanup(); }
  });
});
