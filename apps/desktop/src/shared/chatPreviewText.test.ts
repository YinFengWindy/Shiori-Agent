import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { extractChatPreviewText } from "./chatPreviewText.js";

describe("extractChatPreviewText", () => {
  it("strips emphasis, headings, links and list markers into one line", () => {
    assert.equal(
      extractChatPreviewText("## 今天\n\n- **记得**带伞\n- 看 [天气](https://example.com)\n> 引用一句"),
      "今天 记得带伞 看 天气 引用一句",
    );
  });

  it("replaces fenced code with a placeholder and keeps inline code text", () => {
    assert.equal(extractChatPreviewText("试试 `npm i`：\n```bash\nnpm run dev\n```\n好了"), "试试 npm i： [代码] 好了");
  });

  it("flattens tables and images", () => {
    assert.equal(extractChatPreviewText("![猫](a.png)\n| A | B |\n| --- | --- |\n| 1 | 2 |"), "猫 A B 1 2");
  });

  it("keeps snake_case and arithmetic intact", () => {
    assert.equal(extractChatPreviewText("set max_steps to 2*3"), "set max_steps to 2*3");
  });
});
