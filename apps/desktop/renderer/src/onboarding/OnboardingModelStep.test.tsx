import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "@shiori/sdk/testing";
import { configureSettingsConfigPath, loadSettingsData } from "../../../src/settings";
import { OnboardingModelStep } from "./OnboardingModelStep";

configureSettingsConfigPath("onboarding-recovery-test.toml");

for (const failurePhase of ["read-back", "next-step"] as const) {
  test(`confirmed model saves retry ${failurePhase} recovery with reads and no duplicate write`, async () => {
    let reads = 0;
    let writes = 0;
    let continued = 0;
    let failNext = true;
    let snapshot = { ...loadSettingsData("[llm]\n"), generation: 1 };
    const view = await mountTestComponent(<OnboardingModelStep onBusyChange={() => undefined} onReact={() => undefined} onSaved={async () => {
      if (failurePhase === "next-step" && failNext) { failNext = false; throw new Error("page read failed"); }
      continued += 1;
    }} />, { windowGlobals: { miraDesktop: {
      readSettings: async () => { reads += 1; if (failurePhase === "read-back" && reads === 2) throw new Error("config read failed"); return snapshot; },
      saveSettings: async (formData: typeof snapshot.formData) => { writes += 1; snapshot = { ...snapshot, formData, generation: 2 }; return { ok: true, generation: 2 }; },
    } } });
    try {
      const input = view.container.querySelector<HTMLInputElement>('[aria-label="模型"]');
      assert.ok(input);
      await changeInputValue(input, "model-test");
      await act(async () => view.container.querySelector<HTMLButtonElement>('button[type="submit"]')?.click());
      assert.equal(writes, 1);
      assert.equal(continued, 0);
      assert.equal(view.container.querySelector("fieldset")?.disabled, true);
      assert.match(view.container.querySelector('button[type="submit"]')?.textContent ?? "", /重新加载并继续/);
      const readsBeforeRecovery = reads;
      await act(async () => view.container.querySelector<HTMLButtonElement>('button[type="submit"]')?.click());
      assert.equal(writes, 1);
      assert.equal(reads, readsBeforeRecovery + 1);
      assert.equal(continued, 1);
    } finally { await view.cleanup(); }
  });
}
