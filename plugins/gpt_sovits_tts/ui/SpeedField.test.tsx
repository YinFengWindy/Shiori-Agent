import assert from "node:assert/strict";
import { test } from "node:test";
import { changeInputValue, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { parseSpeed, SpeedField } from "./SpeedField";

test("speeds outside 0.5–2 and blank text are not speeds", () => {
  assert.equal(parseSpeed("1.2"), 1.2);
  assert.equal(parseSpeed("0.5"), 0.5);
  for (const text of ["", " ", "0.4", "2.1", "abc"]) assert.equal(parseSpeed(text), null, text);
});

test("out-of-range input is marked invalid and never written; the stored value re-renders after a reload", async () => {
  const changes: number[] = [];
  const render = (value: number) => <SpeedField value={value} disabled={false} onChange={(speed) => changes.push(speed)} />;
  const view = await mountTestComponent(render(1));
  const input = () => view.container.querySelector<HTMLInputElement>('[aria-label="语速"]')!;
  try {
    assert.equal(input().value, "1");
    assert.equal(input().getAttribute("aria-invalid"), null);
    await changeInputValue(input(), "3");
    assert.deepEqual(changes, []);
    assert.equal(input().value, "3");
    assert.equal(input().getAttribute("aria-invalid"), "true");

    await view.render(render(1.4));
    assert.equal(input().value, "1.4", "a stored value from a reload or retry replaces the typed text");
    assert.equal(input().getAttribute("aria-invalid"), null);

    await changeInputValue(input(), "1.5");
    assert.deepEqual(changes, [1.5]);
    await view.render(render(1.5));
    assert.equal(input().value, "1.5");
  } finally { await view.cleanup(); }
});
