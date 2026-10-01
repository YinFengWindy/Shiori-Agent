import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { createFeedbackRecorder } from "../shared/testing/feedbackRecorder";
import { createDesktopRoleList } from "./desktopRoleList";

test("role-list failures keep their cause without clearing existing roles or caches", async () => {
  const feedback = createFeedbackRecorder();
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: { invoke: async () => ({
    error: { code: "internal_error", message: "本地服务处理失败", details: { detail: "role list denied token=private-value" } },
  }) } } });
  const controller = createDesktopRoleList({ feedback: feedback.reporter,
    setRoles: () => assert.fail("a failure cannot replace roles"),
    setUnreadCounts: () => assert.fail("a failure cannot clear unread counts"),
    retainCachedRoleSessions: () => assert.fail("a failure cannot prune cached sessions"),
  });
  try {
    assert.equal(await controller.loadRolesFromBridge(), null);
    assert.match(feedback.messages("error")[0] ?? "", /角色列表加载失败/);
    assert.match(feedback.messages("error")[0] ?? "", /role list denied/);
    assert.doesNotMatch(feedback.messages("error")[0] ?? "", /private-value/);
  } finally { await view.cleanup(); }
});
