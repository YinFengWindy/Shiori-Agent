import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { RoleChannelBindingsPanel } from "./RoleChannelBindingsPanel";

describe("RoleChannelBindingsPanel", () => {
  it("renders ordered channel rows without a wrapping card surface", () => {
    const markup = renderToStaticMarkup(<RoleChannelBindingsPanel activeRoleId="mira" bindings={[{ channel: "telegram", chat_id: "100", allow_from: ["mira"] }]} onUpdate={() => undefined} />);

    assert.match(markup, /渠道绑定/);
    assert.match(markup, /已配置 1 个投递位置/);
    assert.match(markup, /允许对象/);
    assert.doesNotMatch(markup, /shadow-\[0_12px_30px/);
  });
});
