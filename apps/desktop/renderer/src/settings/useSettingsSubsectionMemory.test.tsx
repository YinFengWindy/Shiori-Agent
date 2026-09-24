import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useSettingsSubsectionMemory, type SettingsSubsectionMemory } from "./useSettingsSubsectionMemory";

async function mountHarness() {
  let latest!: SettingsSubsectionMemory;
  function Harness() {
    latest = useSettingsSubsectionMemory();
    return null;
  }
  const view = await mountTestComponent(<Harness />);
  return { view, memory: () => latest };
}

describe("useSettingsSubsectionMemory", () => {
  it("starts with an empty record and resolves an unvisited section to its first subtab", async () => {
    const { view, memory } = await mountHarness();
    try {
      assert.deepEqual(memory().activeSubsections, {});
      assert.equal(memory().resolve("models"), "catalog");
    } finally { await view.cleanup(); }
  });

  it("remember() is reflected by a later resolve() for the same section", async () => {
    const { view, memory } = await mountHarness();
    try {
      await act(async () => memory().remember("memory", "embedding"));
      assert.equal(memory().activeSubsections.memory, "embedding");
      assert.equal(memory().resolve("memory"), "embedding");
    } finally { await view.cleanup(); }
  });

  it("remember() with the same value already recorded does not create a new record reference (equality guard)", async () => {
    const { view, memory } = await mountHarness();
    try {
      await act(async () => memory().remember("memory", "embedding"));
      const first = memory().activeSubsections;
      await act(async () => memory().remember("memory", "embedding"));
      assert.equal(memory().activeSubsections, first);
    } finally { await view.cleanup(); }
  });

  it("resolve() falls back to the first subtab when the remembered one is filtered out", async () => {
    const { view, memory } = await mountHarness();
    try {
      // "voice" has two static subtabs; simulate an isPluginEnabled filter
      // that would exclude nothing here (no plugin-owned subtabs on
      // "voice"), and separately prove resolve() still honours a genuinely
      // invalid remembered id by falling back to the section's first tab.
      await act(async () => memory().remember("voice", "not-a-real-subtab"));
      assert.equal(memory().resolve("voice"), "provider");
    } finally { await view.cleanup(); }
  });
});
