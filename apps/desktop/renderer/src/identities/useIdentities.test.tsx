import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "@shiori/plugin-sdk";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { useIdentities } from "./useIdentities";

const row = (id: string, boundAt: string) => ({
  id, plugin_id: "qq", user_id: `u-${id}`, scope: "platform", account_id: "", bound_at: boundAt,
});

test("identities reload on identities.updated and only a new binding counts as bound", async () => {
  let rows = [row("a", "2026-09-29T08:00:00+00:00")];
  let emit: ((event: BridgeEvent) => void) | undefined;
  let bound = 0;
  const onBound = () => { bound += 1; };
  function View() {
    const { identities } = useIdentities(onBound);
    return <span>{identities?.map((item) => item.userId).join(",") ?? "loading"}</span>;
  }
  const view = await mountTestComponent(<View />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { emit = listener; return () => undefined; },
    invoke: async ({ method }: { method: string }) =>
      ({ id: "r", type: "response", method, error: null, payload: { identities: rows } }),
  } } });
  const update = () => act(async () => emit?.({ id: "e", type: "event", method: "identities.updated", payload: {} }));
  try {
    assert.equal(view.container.textContent, "u-a");
    assert.equal(bound, 0);
    // A newly known chat changes nothing the list shows as a binding.
    await update();
    assert.equal(bound, 0);
    rows = [...rows, row("b", "2026-09-29T08:05:00+00:00")];
    await update();
    assert.equal(view.container.textContent, "u-a,u-b");
    assert.equal(bound, 1);
    // An unbind is not a binding.
    rows = rows.slice(1);
    await update();
    assert.equal(view.container.textContent, "u-b");
    assert.equal(bound, 1);
  } finally { await view.cleanup(); }
});
