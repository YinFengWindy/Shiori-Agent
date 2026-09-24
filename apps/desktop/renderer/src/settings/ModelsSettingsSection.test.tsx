import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import type { SettingsFormData } from "../shared/types";
import { createSettingsDraft } from "./testFixtures";

let ModelsSettingsSection: typeof import("./ModelsSettingsSection").ModelsSettingsSection;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ ModelsSettingsSection } = await import("./ModelsSettingsSection"));
  await environment.cleanup();
});

/** Renders the catalog against a draft that records every committed update. */
async function mountCatalog() {
  let draft = createSettingsDraft();
  const updates: SettingsFormData[] = [];
  const view = await mountTestComponent(null);
  const render = () => view.render(
    <ModelsSettingsSection
      draft={draft}
      subsectionId="catalog"
      updateDraft={(mutate) => {
        draft = mutate(draft);
        updates.push(draft);
        void render();
      }}
    />,
  );
  await render();
  const button = (label: string) => Array.from(view.container.querySelectorAll<HTMLButtonElement>("button"))
    .find((element) => element.textContent?.includes(label) || element.getAttribute("aria-label") === label)!;
  return { view, updates, draft: () => draft, button };
}

describe("ModelsSettingsSection 「添加模型」", () => {
  it("keeps a new entry out of the saved catalog until it is complete, then saves it once", async () => {
    const catalog = await mountCatalog();
    try {
      await act(async () => catalog.button("添加模型").click());
      assert.match(catalog.view.container.textContent ?? "", /未保存/);
      assert.equal(catalog.updates.length, 0, "opening the form must not persist an empty registration");

      const modelInput = catalog.view.container.querySelector<HTMLInputElement>('input[aria-label="模型"]')!;
      await changeInputValue(modelInput, "gpt-5");
      assert.equal(catalog.updates.length, 1);
      assert.deepEqual(catalog.draft().models.registrations.map((item) => [item.provider, item.model]), [["openai", "gpt-5"]]);
      assert.doesNotMatch(catalog.view.container.textContent ?? "", /未保存/);
    } finally { await catalog.view.cleanup(); }
  });

  it("drops an unfinished entry on back without touching the settings draft", async () => {
    const catalog = await mountCatalog();
    try {
      await act(async () => catalog.button("添加模型").click());
      await act(async () => catalog.button("返回模型注册列表").click());
      assert.equal(catalog.updates.length, 0);
      assert.equal(catalog.draft().models.registrations.length, 0);
      assert.match(catalog.view.container.textContent ?? "", /0 个模型/);
    } finally { await catalog.view.cleanup(); }
  });
});
