import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakeHostServices, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { AgentHandlerLine } from "./AgentHandlerLine";
import { makeRole } from "./testFixtures";

test("the handling role shows with its avatar and current name; without one nothing is reported", async () => {
  const { host } = createFakeHostServices();
  const role = { ...makeRole("role-a", "Mira"), avatar_abs: "D:/roles/mira.png" };
  const view = await mountTestComponent(
    <AgentHandlerLine handler={{ role_id: "role-a", role_name: "旧名" }} findRole={(id) => (id === "role-a" ? role : undefined)} host={host} />,
  );
  try {
    const line = () => view.container.querySelector('[aria-label="接手角色"]');
    assert.equal(line()?.textContent, "接手Mira");
    assert.equal(line()?.querySelector("img")?.getAttribute("alt"), "Mira");

    // A role the host no longer lists keeps the name recorded when it took over.
    await view.render(<AgentHandlerLine handler={{ role_id: "role-x", role_name: "Ayu" }} findRole={() => undefined} host={host} />);
    assert.equal(line()?.textContent, "?接手Ayu");

    await view.render(<AgentHandlerLine handler={null} findRole={() => role} host={host} />);
    assert.equal(line()?.textContent, "无人接手，不会回报");
  } finally { await view.cleanup(); }
});
