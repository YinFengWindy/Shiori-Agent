import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { createFakeHostServices, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { RoutineConfiguration } from "./RoutineConfiguration";

it("copies the exact preview and reports clipboard failure", async () => {
  const services = createFakeHostServices();
  const text = "本机配置\nC:/角色/client.ps1\nC:/角色/client.json";
  const view = await mountTestComponent(<RoutineConfiguration text={text} host={services.host} />);
  const previous = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  let copied = "";
  let fail = false;
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: {
    writeText: async (value: string) => { if (fail) throw new Error("denied"); copied = value; },
  } });
  try {
    assert.equal(document.querySelector("textarea")?.value, text);
    const button = document.querySelector("button");
    assert.ok(button);
    await act(async () => button.click());
    assert.equal(copied, text);
    assert.equal(button.textContent, "已复制");
    fail = true;
    await act(async () => button.click());
    assert.equal(services.feedback.at(-1)?.message, "复制失败");
  } finally {
    if (previous) Object.defineProperty(navigator, "clipboard", previous);
    else Reflect.deleteProperty(navigator, "clipboard");
    await view.cleanup();
  }
});
