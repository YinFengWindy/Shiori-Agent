import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { RoleEmojiSettings } from "./RoleEmojiSettings";

describe("RoleEmojiSettings", () => {
  it("renders the global role emoji allowlist with add and delete actions", () => {
    const markup = renderToStaticMarkup(
      <RoleEmojiSettings
        entries={[{ name: "heart", value: "❤️" }]}
        onChange={() => undefined}
      />,
    );

    assert.match(markup, /aria-label="添加 Emoji"/);
    assert.match(markup, /value="heart"/);
    assert.match(markup, /value="❤️"/);
    assert.match(markup, /aria-label="删除 Emoji 1"/);
  });
});
