import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { AccountStatusDot, statusDotTone } from "./AccountStatusDot";

test("status tones map to the green / yellow / red / gray dot colors", () => {
  assert.equal(statusDotTone("success"), "bg-success");
  assert.equal(statusDotTone("warning"), "bg-warning");
  assert.equal(statusDotTone("danger"), "bg-danger");
  assert.equal(statusDotTone("muted"), "bg-ink-faint");
});

test("a bare dot is named by its status; with text the dot is decorative", async () => {
  const view = await mountTestComponent(<AccountStatusDot status={{ label: "在线", tone: "success" }} />);
  try {
    const dot = view.container.querySelector('[role="img"]');
    assert.equal(dot?.getAttribute("aria-label"), "在线");
    assert.ok(dot?.classList.contains("bg-success"));
    await view.render(<AccountStatusDot withText status={{ label: "正在连接", tone: "warning" }} />);
    assert.equal(view.container.querySelector('[role="img"]'), null);
    assert.equal(view.container.textContent, "正在连接");
    assert.ok(view.container.querySelector('[aria-hidden="true"]')?.classList.contains("bg-warning"));
  } finally { await view.cleanup(); }
});
