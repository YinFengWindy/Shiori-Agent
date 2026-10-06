import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createRoleUiDirtyLease, usePluginRoleUiDirty } from "./pluginRoleUiDirty";

test("independent editors keep navigation dirty and a disposed report cannot clear a successor", async () => {
  const old = createRoleUiDirtyLease("role"); const next = createRoleUiDirtyLease("role");
  function Probe() { const dirty = usePluginRoleUiDirty("role"); return <span>{String(dirty)}</span>; }
  const view = await mountTestComponent(<Probe />);
  try {
    await act(async () => old.set(true)); assert.equal(view.container.textContent, "true");
    await act(async () => { old.dispose(); next.set(true); });
    await act(async () => old.set(false)); assert.equal(view.container.textContent, "true");
    await act(async () => next.set(false)); assert.equal(view.container.textContent, "false");
  } finally { old.dispose(); next.dispose(); await view.cleanup(); }
});
