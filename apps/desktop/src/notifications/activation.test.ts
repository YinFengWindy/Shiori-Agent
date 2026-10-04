import assert from "node:assert/strict";
import { test } from "node:test";
import { NotificationActivation, notificationActivationUrl } from "./activation.js";

const protocol = "shiori-notification";

test("cold protocol launches retain the target until initialization and renderer acknowledgement", () => {
  let revealed = 0;
  const activation = new NotificationActivation(protocol, () => { revealed += 1; });
  assert.equal(activation.handleArguments(["D:\\Shiori\\Shiori.exe", notificationActivationUrl(protocol, "吟风 & friends")]), true);
  assert.equal(revealed, 0);
  activation.markReady();
  assert.equal(revealed, 1);
  const target = activation.navigation.getPending()!;
  assert.equal(target.roleId, "吟风 & friends");
  assert.deepEqual(activation.navigation.getPending(), target);
  activation.navigation.acknowledge(target.id);
  assert.equal(activation.navigation.getPending(), null);
});

test("later process activation restores the window and replaces an earlier pending chat", () => {
  let revealed = 0;
  const activation = new NotificationActivation(protocol, () => { revealed += 1; });
  activation.markReady();
  activation.openChat("first");
  const first = activation.navigation.getPending()!;
  activation.handleArguments(["--original-process-start-time=123", notificationActivationUrl(protocol, "second")]);
  activation.navigation.acknowledge(first.id);
  assert.equal(activation.navigation.getPending()?.roleId, "second");
  assert.equal(revealed, 2);
});

test("untrusted command-line data cannot invoke other routes or cross the development identity", () => {
  const activation = new NotificationActivation(protocol, () => assert.fail("must not activate"));
  activation.markReady();
  for (const value of [
    "https://notification/chat?roleId=mira",
    "shiori-notification-dev-abc://notification/chat?roleId=mira",
    "shiori-notification://notification/settings?roleId=mira",
    "shiori-notification://notification/chat?roleId=",
    "shiori-notification://notification/chat?roleId=%GG",
    "shiori-notification://notification/chat?roleId=%00",
    "shiori-notification://notification/chat?roleId=%ED%A0%80",
    "shiori-notification://notification/chat?roleId=mira&roleId=other",
    "shiori-notification://notification/chat?roleId=mira&url=https://example.com",
    "shiori-notification://notification/chat?roleId=mira#extra",
    "shiori-notification://user@notification/chat?roleId=mira",
    "shiori-notification://notification:42/chat?roleId=mira",
    "shiori-notification://notification/other/../chat?roleId=mira",
    notificationActivationUrl(protocol, "a".repeat(513)),
    "--inspect=9229",
  ]) assert.equal(activation.handleArguments([value]), false, value);
  assert.equal(activation.navigation.getPending(), null);
});

test("quotes, paths and URL-looking role IDs remain data in the canonical chat target", () => {
  const activation = new NotificationActivation(protocol, () => {});
  const roleId = '" & start calc.exe & C:\\some path\\..\\角色 https://example.com';
  assert.equal(activation.handleArguments([notificationActivationUrl(protocol, roleId)]), true);
  assert.equal(activation.navigation.getPending()?.roleId, roleId);
});

test("ordinary second launches wait for readiness and failed window opens do not consume the chat", () => {
  let attempts = 0;
  const activation = new NotificationActivation(protocol, () => {
    if (++attempts === 1) throw new Error("window unavailable");
  });
  activation.requestWindow();
  activation.openChat("mira");
  assert.equal(attempts, 0);
  assert.throws(() => activation.markReady(), /window unavailable/);
  activation.markReady();
  assert.equal(attempts, 2);
  assert.equal(activation.navigation.getPending()?.roleId, "mira");
});
