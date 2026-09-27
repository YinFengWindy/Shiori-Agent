import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { deferred } from "./memoryTestBridge";
import { useMemoryRead } from "./useMemoryRead";

type Batch = { items: string[] };

function Probe({ scope, page, read }: { scope: string; page: number; read: (key: string) => Promise<Batch> }) {
  const key = `${scope}#${page}`;
  const state = useMemoryRead<Batch>({ scope, key, read: () => read(key), merge: (previous, next) => ({ items: [...previous.items, ...next.items] }) });
  return <p>{[state.loading ? "loading" : "idle", state.error, state.value?.items.join(",") ?? "none", state.last?.items.join(",") ?? "none"].join("|")}</p>;
}

it("drops a response whose key is no longer current", async () => {
  const pending = new Map<string, ReturnType<typeof deferred<Batch>>>();
  const read = (key: string) => {
    const next = deferred<Batch>();
    pending.set(key, next);
    return next.promise;
  };
  const view = await mountTestComponent(<Probe scope="mira" page={1} read={read} />);
  try {
    assert.equal(view.container.textContent, "loading||none|none");
    await view.render(<Probe scope="atlas" page={1} read={read} />);
    await act(async () => pending.get("mira#1")?.resolve({ items: ["mira secret"] }));
    assert.equal(view.container.textContent, "loading||none|none");
    await act(async () => pending.get("atlas#1")?.resolve({ items: ["a1"] }));
    assert.equal(view.container.textContent, "idle||a1|a1");
  } finally {
    await view.cleanup();
  }
});

it("appends batches within a scope, resets on a new scope, and keeps the last value across failures", async () => {
  const pending = new Map<string, ReturnType<typeof deferred<Batch>>>();
  const read = (key: string) => {
    const next = deferred<Batch>();
    pending.set(key, next);
    return next.promise;
  };
  const view = await mountTestComponent(<Probe scope="q1" page={1} read={read} />);
  try {
    await act(async () => pending.get("q1#1")?.resolve({ items: ["a"] }));
    await view.render(<Probe scope="q1" page={2} read={read} />);
    // The next batch loads under the items already shown.
    assert.equal(view.container.textContent, "loading||a|a");
    await act(async () => pending.get("q1#2")?.resolve({ items: ["b"] }));
    assert.equal(view.container.textContent, "idle||a,b|a,b");
    await view.render(<Probe scope="q2" page={1} read={read} />);
    assert.equal(view.container.textContent, "loading||none|a,b");
    await act(async () => pending.get("q2#1")?.reject(new Error("offline")));
    assert.equal(view.container.textContent, "idle|offline|none|a,b");
  } finally {
    await view.cleanup();
  }
});
