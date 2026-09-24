import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { PromptTagGrid } from "./PromptTagGrid";
import type { PromptTagEntry } from "./types";

const entry: PromptTagEntry = {
  id: "smile", name: "微笑", enabled: false, category: "expression", match_terms: ["笑"], positive_tags: ["smile"], negative_tags: [], rating: "general", image_path: "",
};

describe("PromptTagGrid", () => {
  it("an empty library shows the brand empty state whose one action creates an entry", async () => {
    let creates = 0;
    const view = await mountTestComponent(<PromptTagGrid entries={[]} loaded onOpen={() => undefined} onCreate={() => { creates += 1; }} onDelete={() => undefined} />);
    try {
      const empty = view.container.querySelector('[data-testid="prompt-tag-empty"]');
      assert.ok(empty);
      await act(async () => empty.querySelector("button")?.click());
      assert.equal(creates, 1);
    } finally { await view.cleanup(); }
  });

  it("does not flash the empty state before the first load", async () => {
    const view = await mountTestComponent(<PromptTagGrid entries={[]} loaded={false} onOpen={() => undefined} onCreate={() => undefined} onDelete={() => undefined} />);
    try {
      assert.equal(view.container.querySelector('[data-testid="prompt-tag-empty"]'), null);
    } finally { await view.cleanup(); }
  });

  it("lists entries with their category and a disabled badge, and opens one on click", async () => {
    const opened: string[] = [];
    const view = await mountTestComponent(<PromptTagGrid entries={[entry]} loaded onOpen={(item) => opened.push(item.id)} onCreate={() => undefined} onDelete={() => undefined} />);
    try {
      assert.match(view.container.textContent ?? "", /1 条/);
      assert.match(view.container.textContent ?? "", /expression/);
      assert.match(view.container.textContent ?? "", /已停用/);
      await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="打开 微笑"]')?.click());
      assert.deepEqual(opened, ["smile"]);
    } finally { await view.cleanup(); }
  });
});
