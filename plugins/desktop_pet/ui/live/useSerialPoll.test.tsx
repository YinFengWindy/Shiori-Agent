import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useSerialPoll } from "./useSerialPoll";

function Poller({ active, tick }: { active: boolean; tick: () => Promise<void> }) {
  useSerialPoll(active, 1000, tick);
  return null;
}

test("a slow answer delays the next request instead of overlapping it, and turning off stops the loop", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const answers: Array<ReturnType<typeof deferred<void>>> = [];
  const tick = () => { const answer = deferred<void>(); answers.push(answer); return answer.promise; };
  const view = await mountTestComponent(<Poller active tick={tick} />);
  try {
    assert.equal(answers.length, 0, "the first request waits one interval");
    await act(async () => t.mock.timers.tick(1000));
    assert.equal(answers.length, 1);
    await act(async () => t.mock.timers.tick(5000));
    assert.equal(answers.length, 1, "no second request while the first is unanswered");
    await act(async () => answers[0].resolve());
    await act(async () => t.mock.timers.tick(999));
    assert.equal(answers.length, 1, "the interval restarts after the answer");
    await act(async () => t.mock.timers.tick(1));
    assert.equal(answers.length, 2);

    await view.render(<Poller active={false} tick={tick} />);
    await act(async () => answers[1].resolve());
    await act(async () => t.mock.timers.tick(10_000));
    assert.equal(answers.length, 2, "an answer after turning off schedules nothing");
  } finally { await view.cleanup(); }
});

test("a loop restarted while a call is in flight waits for that call before its first wait", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const answers: Array<ReturnType<typeof deferred<void>>> = [];
  const tick = () => { const answer = deferred<void>(); answers.push(answer); return answer.promise; };
  const view = await mountTestComponent(<Poller active tick={tick} />);
  try {
    await act(async () => t.mock.timers.tick(1000));
    assert.equal(answers.length, 1);
    // e.g. the dialog closed and reopened within one interval
    await view.render(<Poller active={false} tick={tick} />);
    await view.render(<Poller active tick={tick} />);
    await act(async () => t.mock.timers.tick(5000));
    assert.equal(answers.length, 1, "the restarted loop never overlaps the call in flight");
    await act(async () => answers[0].resolve());
    await act(async () => t.mock.timers.tick(1000));
    assert.equal(answers.length, 2, "it starts one interval after that call settled");
    await act(async () => answers[1].resolve());
    await act(async () => t.mock.timers.tick(1000));
    assert.equal(answers.length, 3, "and only one loop runs");
  } finally { await view.cleanup(); }
});
