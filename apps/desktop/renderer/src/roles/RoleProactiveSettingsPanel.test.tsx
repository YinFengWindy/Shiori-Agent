import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";

test("proactive settings do not expose legacy bound target candidates", () => {
  const markup = renderToStaticMarkup(
    <RoleProactiveSettingsPanel
      roleForm={{
        ...createEmptyRoleForm(),
        proactiveEnabled: true,
      }}
      onUpdate={() => undefined}
    />,
  );

  assert.match(markup, /主动推送/);
  assert.match(markup, /推送策略/);
  assert.match(markup, /执行参数/);
  assert.doesNotMatch(markup, /接收会话|渠道绑定|gqq:42|type="checkbox"/);
});
