import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { act, useEffect } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { getFeedbackSnapshot, resetFeedback } from "../shared/feedback/feedbackStore";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleProactiveCandidate } from "../shared/types";
import { useRoleProactiveTarget, type RoleProactiveTargetPreview } from "./useRoleProactiveTarget";

const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

const desktop = { channel: "desktop", chat_id: "role:mira" };
const qq = { channel: "qq", chat_id: "10001" };

afterEach(() => resetFeedback());

async function mountTarget(preview: RoleProactiveTargetPreview, initial: RoleProactiveCandidate[]) {
  const listeners = new Set<(event: BridgeEvent) => void>();
  let latest: RoleProactiveCandidate | null = null;
  function Probe({ candidates }: { candidates: RoleProactiveCandidate[] }) {
    const target = useRoleProactiveTarget("mira", candidates, preview);
    useEffect(() => { latest = target; });
    return null;
  }
  const view = await mountTestComponent(<Probe candidates={initial} />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  } } });
  await flush();
  return {
    view,
    get latest() { return latest; },
    async setCandidates(next: RoleProactiveCandidate[]) {
      await view.render(<Probe candidates={next} />);
      await flush();
    },
    async emit(method: string) {
      await act(async () => {
        for (const listener of [...listeners]) listener({ id: "e", type: "event", method, payload: {} } as BridgeEvent);
      });
      await flush();
    },
  };
}

test("asks the backend for the current target and refreshes on new messages, not on unrelated events", async () => {
  const calls: RoleProactiveCandidate[][] = [];
  let answer: RoleProactiveCandidate = desktop;
  const target = await mountTarget(async (roleId, candidates) => {
    assert.equal(roleId, "mira");
    calls.push(candidates);
    return answer;
  }, [desktop, qq]);
  try {
    assert.deepEqual(target.latest, desktop);
    answer = qq;
    await target.emit("session.updated");
    assert.deepEqual(target.latest, qq);
    await target.emit("runtime.applied");
    assert.equal(calls.length, 2);

    // An equal list does not ask again; a changed one does.
    await target.setCandidates([{ ...desktop }, { ...qq }]);
    assert.equal(calls.length, 2);
    await target.setCandidates([qq]);
    assert.deepEqual(calls.at(-1), [qq]);
  } finally {
    await target.view.cleanup();
  }
});

test("has no target without candidates and never asks", async () => {
  let calls = 0;
  const target = await mountTarget(async () => { calls += 1; return desktop; }, []);
  try {
    assert.equal(target.latest, null);
    assert.equal(calls, 0);
  } finally {
    await target.view.cleanup();
  }
});

test("clears the mark and reports a failed preview", async () => {
  const target = await mountTarget(async () => { throw new Error("bridge offline"); }, [desktop]);
  try {
    assert.equal(target.latest, null);
    assert.deepEqual(getFeedbackSnapshot().map((toast) => [toast.tone, toast.message]), [["error", "主动推送接收会话加载失败：bridge offline"]]);
  } finally {
    await target.view.cleanup();
  }
});
