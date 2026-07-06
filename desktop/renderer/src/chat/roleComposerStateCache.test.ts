/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  createChatComposerStateSnapshot,
  readRoleComposerStateCache,
  retainRoleComposerStateCache,
  writeRoleComposerStateCache,
} from "./roleComposerStateCache";

describe("roleComposerStateCache", () => {
  it("normalizes snapshot fields for one role", () => {
    const snapshot = createChatComposerStateSnapshot({
      draft: "hello",
      attachments: [" D:\\images\\one.png ", "", "D:\\docs\\two.md"],
      replyTarget: {
        messageId: "message-1",
        sender: "Mira",
        content: "继续说",
        preview: "继续说",
      },
    });

    assert.deepEqual(snapshot, {
      draft: "hello",
      attachments: ["D:\\images\\one.png", "D:\\docs\\two.md"],
      replyTarget: {
        messageId: "message-1",
        sender: "Mira",
        content: "继续说",
        preview: "继续说",
      },
    });
  });

  it("reads and writes cached composer state by role id", () => {
    const cache = writeRoleComposerStateCache(
      {},
      " mira ",
      createChatComposerStateSnapshot({ draft: "pending message" }),
    );

    assert.deepEqual(readRoleComposerStateCache(cache, "mira"), {
      draft: "pending message",
      attachments: [],
      replyTarget: null,
    });
  });

  it("retains only roles that still exist in the latest role list", () => {
    const cache = {
      mira: createChatComposerStateSnapshot({ draft: "keep" }),
      shiori: createChatComposerStateSnapshot({ draft: "drop" }),
    };

    assert.deepEqual(retainRoleComposerStateCache(cache, ["mira"]), {
      mira: createChatComposerStateSnapshot({ draft: "keep" }),
    });
  });
});
