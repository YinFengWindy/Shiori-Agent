import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { RoleCapabilityCard } from "./RoleCapabilityCard";

const status = { label: "已启用", tone: "on" } as const;

test("a capability card offers the ⚙ only when it has settings", () => {
  const plain = renderToStaticMarkup(<RoleCapabilityCard icon={null} title="NSFW 记忆" status={status} control={<button type="button" role="switch" aria-checked="true" />} />);
  assert.doesNotMatch(plain, /设置/);

  const configurable = renderToStaticMarkup(<RoleCapabilityCard icon={null} title="桌宠" status={status} settings={<div />} control={<button type="button" role="switch" aria-checked="true" />} />);
  assert.match(configurable, /aria-label="桌宠设置"/);
  // The ⚙ follows the switch at the end of the title row.
  assert.ok(configurable.indexOf('role="switch"') < configurable.indexOf('aria-label="桌宠设置"'));
});
