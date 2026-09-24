/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { ChatErrorRow } from "./ChatErrorRow";

describe("ChatErrorRow", () => {
  it("keeps the message and reveals the reported cause behind 详情", async () => {
    const view = await mountTestComponent(
      <ChatErrorRow content="处理消息时出错，请稍后再试。" detail="APIStatusError: 502 Bad Gateway" canRetry onRetry={() => undefined} />,
    );
    try {
      assert.match(view.container.textContent ?? "", /处理消息时出错/);
      assert.doesNotMatch(view.container.textContent ?? "", /502 Bad Gateway/);
      const toggle = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent?.includes("详情"));
      await act(async () => { toggle?.click(); });
      assert.match(view.container.textContent ?? "", /APIStatusError: 502 Bad Gateway/);
    } finally { await view.cleanup(); }
  });

  it("offers retry only when the turn can be retried", async () => {
    let retried = 0;
    const view = await mountTestComponent(<ChatErrorRow content="出错了" canRetry={false} onRetry={() => { retried += 1; }} />);
    try {
      assert.equal(view.container.querySelector('[data-testid="chat-error-retry"]'), null);
      await view.render(<ChatErrorRow content="出错了" canRetry onRetry={() => { retried += 1; }} />);
      await act(async () => { view.container.querySelector<HTMLButtonElement>('[data-testid="chat-error-retry"]')?.click(); });
      assert.equal(retried, 1);
    } finally { await view.cleanup(); }
  });
});
