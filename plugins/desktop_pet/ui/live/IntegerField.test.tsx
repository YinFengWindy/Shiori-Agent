import assert from "node:assert/strict";
import { test } from "node:test";
import { changeInputValue, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { IntegerField, parseInteger } from "./IntegerField";

test("only whole numbers in range parse; blank is null only for an optional field", () => {
  assert.equal(parseInteger("300", { min: 0, max: 300 }), 300);
  assert.equal(parseInteger(" 0 ", { min: 0, max: 300 }), 0);
  assert.equal(parseInteger("", { min: 1, optional: true }), null);
  for (const text of ["", "301", "-1", "1.5", "abc"]) assert.equal(parseInteger(text, { min: 0, max: 300 }), undefined, text);
  assert.equal(parseInteger("0", { min: 1, optional: true }), undefined);
});

test("invalid input is marked and never written; a stored value replaces the typed text", async () => {
  const changes: Array<number | null> = [];
  const render = (value: number | null) => <IntegerField label="直播间号" value={value} min={1} optional disabled={false} onChange={(next) => changes.push(next)} />;
  const view = await mountTestComponent(render(null));
  const input = () => view.container.querySelector<HTMLInputElement>('[aria-label="直播间号"]')!;
  try {
    assert.equal(input().value, "");
    assert.equal(input().getAttribute("aria-invalid"), null);
    await changeInputValue(input(), "0");
    assert.deepEqual(changes, []);
    assert.equal(input().getAttribute("aria-invalid"), "true");
    assert.match(input().className, /border-danger/);

    await changeInputValue(input(), "12345");
    assert.deepEqual(changes, [12345]);
    await view.render(render(12345));
    assert.equal(input().value, "12345");
    assert.equal(input().getAttribute("aria-invalid"), null);

    await view.render(render(678));
    assert.equal(input().value, "678", "a reload shows the stored room");
    await changeInputValue(input(), "");
    assert.deepEqual(changes, [12345, null], "clearing an optional field writes null");
  } finally { await view.cleanup(); }
});
