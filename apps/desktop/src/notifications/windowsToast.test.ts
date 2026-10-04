import assert from "node:assert/strict";
import { test } from "node:test";
import { Window } from "happy-dom";
import { pathToFileURL } from "node:url";
import { NotificationActivation } from "./activation.js";
import { windowsNotificationToast } from "./windowsToast.js";

test("the actual toast XML carries a durable protocol activation and PNG app artwork", () => {
  const window = new Window();
  const roleId = '吟风 " & <friend>';
  const title = '<text hint="x"> & "role"';
  const body = "hello & goodbye </text></binding><actions/>";
  const iconPath = "D:\\Shiori App\\assets\\shiori-app-icon.png";
  const xml = windowsNotificationToast({ protocol: "shiori-notification", roleId, title, body, iconPath });
  const document = new window.DOMParser().parseFromString(xml, "text/xml");
  const toast = document.documentElement;
  assert.equal(toast.tagName, "toast");
  assert.equal(toast.getAttribute("activationType"), "protocol");
  assert.equal(document.querySelectorAll("text").length, 2);
  assert.equal(document.querySelectorAll("text")[0]?.textContent, title);
  assert.equal(document.querySelectorAll("text")[1]?.textContent, body);
  assert.equal(document.querySelector("actions"), null);
  assert.equal(document.querySelector("image")?.getAttribute("src"), pathToFileURL(iconPath).href);
  const activation = new NotificationActivation("shiori-notification", () => {});
  assert.equal(activation.handleArguments([toast.getAttribute("launch")!]), true);
  assert.equal(activation.navigation.getPending()?.roleId, roleId);
});

test("invalid XML characters in message content cannot break notification delivery", () => {
  const xml = windowsNotificationToast({
    protocol: "shiori-notification", roleId: "mira", iconPath: "C:\\icon.png",
    title: `role${String.fromCharCode(0, 1, 0xd800, 0xfffe)}`,
    body: "emoji 🌸\tand\nnewline",
  });
  assert.ok(xml.includes("<text>role</text>"));
  assert.ok(xml.includes("emoji 🌸\tand\nnewline"));
});
