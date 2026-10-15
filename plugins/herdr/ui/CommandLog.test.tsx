import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { CommandLog } from "./CommandLog";
import { makeCommand } from "./testFixtures";

test("a delivered command says whether it is reported; one that never reached the agent does not", async () => {
  const mira = { kind: "role" as const, role_id: "role-a", role_name: "Mira" };
  const view = await mountTestComponent(
    <CommandLog
      commands={[
        makeCommand({ id: "a", content: "看看", report: "none" }),
        makeCommand({ id: "b", content: "修滚动", source: mira, report: "pending" }),
        makeCommand({ id: "c", content: "补测试", source: mira, status: "unconfirmed", error: "未确认", report: "reported" }),
        makeCommand({ id: "d", content: "跑一遍", report: "failed", report_error: "角色绑定已失效" }),
        makeCommand({ id: "e", content: "再来", status: "failed", error: "Agent 已关闭，未发送。" }),
      ]}
    />,
  );
  try {
    const rows = Array.from(view.container.querySelectorAll('[aria-label="指令记录"] li > div'), (row) => row.textContent);
    assert.deepEqual(rows, [
      "你不回报看看",
      "Mira待回报修滚动",
      "Mira未确认送达已回报补测试未确认",
      "你回报失败跑一遍角色绑定已失效",
      "你未发送再来Agent 已关闭，未发送。",
    ]);
  } finally { await view.cleanup(); }
});
