import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act, useState } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import type { SelectOption } from "./Select";

let Select: typeof import("./Select").Select;
before(async () => {
  // Headless UI chooses browser layout effects when its module is first loaded.
  const environment = await mountTestComponent(null);
  ({ Select } = await import("./Select"));
  await environment.cleanup();
});

const options: SelectOption[] = [
  { value: "", label: "System default" },
  { value: "offline", label: "Offline", disabled: true },
  { value: "microphone", label: "Microphone" },
];

function Picker({ onChange }: { onChange: (value: string) => void }) {
  const [value, setValue] = useState("");
  return <Select aria-label="Input device" value={value} options={options} onValueChange={(next) => { setValue(next); onChange(next); }} />;
}

function trigger() {
  const element = document.querySelector<HTMLButtonElement>('[role="combobox"]');
  assert.ok(element);
  return element;
}

async function press(key: string) {
  await act(async () => {
    document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  });
}

describe("Select", () => {
  it("selects with pointer events through a portal and preserves the empty value", async () => {
    const changes: string[] = [];
    const view = await mountTestComponent(<Picker onChange={(value) => changes.push(value)} />);
    try {
      assert.equal(trigger().textContent, "System default");
      await act(async () => trigger().click());
      const list = document.querySelector('[role="listbox"]');
      assert.ok(list);
      assert.equal(view.container.contains(list), false);
      const items = document.querySelectorAll<HTMLElement>('[role="option"]');
      await act(async () => items[2].click());
      assert.deepEqual(changes, ["microphone"]);
      assert.equal(trigger().textContent, "Microphone");
      assert.equal(trigger().getAttribute("aria-expanded"), "false");
      assert.equal(document.activeElement, trigger());
      await act(async () => trigger().click());
      await act(async () => document.querySelector<HTMLElement>('[role="option"]')?.click());
      assert.deepEqual(changes, ["microphone", ""]);
      assert.equal(trigger().textContent, "System default");
    } finally { await view.cleanup(); }
  });

  it("shows an option's trigger label when closed and its full label in the list", async () => {
    const annotated: SelectOption[] = [{ value: "qqbot", label: "QQBot（未配置）", triggerLabel: "QQBot" }, { value: "desktop", label: "桌面端" }];
    const view = await mountTestComponent(<Select aria-label="Input device" value="qqbot" options={annotated} onValueChange={() => undefined} />);
    try {
      assert.equal(trigger().textContent, "QQBot");
      await act(async () => trigger().click());
      assert.deepEqual(Array.from(document.querySelectorAll('[role="option"]'), (item) => item.textContent), ["QQBot（未配置）", "桌面端"]);
    } finally { await view.cleanup(); }
  });

  it("opens by keyboard, skips disabled options, confirms and cancels without changing values", async () => {
    const changes: string[] = [];
    const view = await mountTestComponent(<Picker onChange={(value) => changes.push(value)} />);
    try {
      await act(async () => trigger().focus());
      await press("ArrowDown");
      assert.equal(trigger().getAttribute("aria-expanded"), "true");
      await press("End");
      await press("Enter");
      assert.deepEqual(changes, ["microphone"]);
      await press(" ");
      await press("Home");
      await press("ArrowDown");
      await press("Enter");
      assert.deepEqual(changes, ["microphone"]);
      await press("Enter");
      await press("Home");
      await press("Escape");
      assert.deepEqual(changes, ["microphone"]);
      assert.equal(trigger().getAttribute("aria-expanded"), "false");
      assert.equal(document.activeElement, trigger());
    } finally { await view.cleanup(); }
  });

  it("updates controlled values and labels without emitting changes when options arrive or disappear", async () => {
    const changes: string[] = [];
    const onValueChange = (value: string) => changes.push(value);
    const view = await mountTestComponent(<Select aria-label="Input device" value="microphone" options={[]} onValueChange={onValueChange} />);
    try {
      await view.render(<Select aria-label="Input device" value="microphone" options={options} onValueChange={onValueChange} />);
      assert.equal(trigger().textContent, "Microphone");
      await view.render(<Select aria-label="Input device" value="microphone" options={[{ value: "microphone", label: "Renamed device" }]} onValueChange={onValueChange} />);
      assert.equal(trigger().textContent, "Renamed device");
      await view.render(<Select aria-label="Input device" value="" options={options} onValueChange={onValueChange} disabled />);
      await act(async () => trigger().click());
      assert.equal(trigger().disabled, true);
      assert.equal(trigger().getAttribute("aria-expanded"), "false");
      assert.equal(trigger().textContent, "System default");
      assert.deepEqual(changes, []);
    } finally { await view.cleanup(); }
  });

  it("dismisses on an outside pointer without committing the highlighted option", async () => {
    const changes: string[] = [];
    const view = await mountTestComponent(<><Picker onChange={(value) => changes.push(value)} /><button id="after">Next field</button></>);
    try {
      await act(async () => trigger().click());
      await press("End");
      const outside = document.getElementById("after");
      assert.ok(outside);
      await act(async () => {
        outside.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, pointerType: "mouse" }));
        outside.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
        outside.click();
      });
      assert.equal(trigger().getAttribute("aria-expanded"), "false");
      assert.deepEqual(changes, []);
    } finally { await view.cleanup(); }
  });

  it("shows an option's icon in its row and, once selected, in the trigger", async () => {
    const withIcons: SelectOption[] = [
      { value: "rin", label: "Rin", icon: <img data-testid="icon-rin" alt="" /> },
      { value: "kaede", label: "Kaede", icon: <span data-testid="icon-kaede">K</span> },
    ];
    const changes: string[] = [];
    function IconPicker() {
      const [value, setValue] = useState("rin");
      return <Select aria-label="Role" value={value} options={withIcons} onValueChange={(next) => { setValue(next); changes.push(next); }} />;
    }
    const view = await mountTestComponent(<IconPicker />);
    try {
      assert.ok(trigger().querySelector('[data-testid="icon-rin"]'));
      assert.equal(trigger().textContent, "Rin");
      await act(async () => trigger().click());
      const rows = document.querySelectorAll<HTMLElement>('[role="option"]');
      assert.ok(rows[1].querySelector('[data-testid="icon-kaede"]'));
      await act(async () => rows[1].click());
      assert.deepEqual(changes, ["kaede"]);
      assert.ok(trigger().querySelector('[data-testid="icon-kaede"]'));
      assert.equal(trigger().querySelector('[data-testid="icon-rin"]'), null);
    } finally { await view.cleanup(); }
  });
});
