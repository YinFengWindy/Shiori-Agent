import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { changeInputValue, mountTestComponent } from "../testing/domTestHarness";
import { StringListInput } from "./StringListInput";

/** Keeps the list in state so every edit round-trips through `onChange`. */
function Harness({ initial, onChange }: { initial: string[]; onChange: (items: string[]) => void }) {
  const [items, setItems] = useState(initial);
  return <StringListInput ariaLabel="黑名单" items={items} inputClassName="field" addButtonClassName="add" placeholder="QQ 号" onChange={(next) => { setItems(next); onChange(next); }} />;
}

describe("StringListInput", () => {
  it("adds trimmed unique entries with the button and removes a chip", async () => {
    const changes: string[][] = [];
    const view = await mountTestComponent(<Harness initial={["1"]} onChange={(next) => changes.push(next)} />);
    try {
      const input = view.container.querySelector<HTMLInputElement>('input[aria-label="输入黑名单"]');
      const add = view.container.querySelector<HTMLButtonElement>('button[aria-label="添加黑名单"]');
      assert.ok(input && add);
      assert.equal(input.placeholder, "QQ 号");
      assert.equal(add.disabled, true);

      await changeInputValue(input, " 2 ");
      await act(async () => add.click());
      await changeInputValue(input, "1");
      await act(async () => add.click());
      assert.deepEqual(changes, [["1", "2"]]);
      assert.equal(input.value, "");

      const remove = view.container.querySelector<HTMLButtonElement>('button[aria-label="移除 1"]');
      assert.ok(remove);
      await act(async () => remove.click());
      assert.deepEqual(changes.at(-1), ["2"]);
    } finally {
      await view.cleanup();
    }
  });

  it("adds on Enter and removes the last chip on Backspace in an empty input", async () => {
    const changes: string[][] = [];
    const view = await mountTestComponent(<Harness initial={["1"]} onChange={(next) => changes.push(next)} />);
    try {
      const input = view.container.querySelector<HTMLInputElement>('input[aria-label="输入黑名单"]');
      assert.ok(input);
      await changeInputValue(input, "2");
      await act(async () => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
      await act(async () => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Backspace", bubbles: true })); });
      assert.deepEqual(changes, [["1", "2"], ["1"]]);
    } finally {
      await view.cleanup();
    }
  });

  it("shows only the chips when read-only", () => {
    const markup = renderToStaticMarkup(<StringListInput ariaLabel="黑名单" items={["1", "2"]} inputClassName="field" addButtonClassName="add" readOnly onChange={() => undefined} />);

    assert.match(markup, /<span class="truncate font-mono">1<\/span>/);
    assert.match(markup, /<span class="truncate font-mono">2<\/span>/);
    assert.doesNotMatch(markup, /<input|<button|移除/);
  });
});
