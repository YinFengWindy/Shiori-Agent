import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { windowsNotificationIdentity } from "./windowsIdentity.js";

const options = {
  packaged: true,
  appPath: "D:\\Shiori App\\resources\\app.asar",
  userDataPath: "C:\\Users\\example\\AppData\\Roaming\\Shiori",
  executablePath: "D:\\Shiori App\\Shiori.exe",
  iconPath: "D:\\Shiori App\\resources\\assets\\shiori-app-icon.png",
};

test("installed notification identity matches packaging and launches the actual exe with its profile", () => {
  const identity = windowsNotificationIdentity(options);
  const packaging = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8"));
  assert.equal(identity.appId, packaging.build.appId);
  assert.equal(identity.name, packaging.build.productName);
  assert.equal(identity.executablePath, options.executablePath);
  assert.deepEqual(identity.arguments, [`--shiori-user-data-dir=${options.userDataPath}`]);
  assert.equal(identity.protocol, "shiori-notification");
});

test("development registrations cannot replace installed identity, protocol or a different checkout/profile", () => {
  const installed = windowsNotificationIdentity(options);
  const development = windowsNotificationIdentity({ ...options, packaged: false, appPath: "D:\\Shiori Source\\apps\\desktop" });
  assert.notEqual(development.appId, installed.appId);
  assert.notEqual(development.protocol, installed.protocol);
  assert.equal(development.name, "Shiori (Development)");
  assert.deepEqual(development.arguments, ["D:\\Shiori Source\\apps\\desktop", `--shiori-user-data-dir=${options.userDataPath}`]);
  for (const changes of [{ appPath: "D:\\Other Checkout\\apps\\desktop" }, { userDataPath: "C:\\Test Profile" }]) {
    const other = windowsNotificationIdentity({ ...options, packaged: false, ...changes });
    assert.notEqual(other.appId, development.appId);
    assert.notEqual(other.protocol, development.protocol);
  }
});

test("the same Windows paths keep a stable development identity despite case and separator differences", () => {
  const first = windowsNotificationIdentity({ ...options, packaged: false });
  const next = windowsNotificationIdentity({
    ...options, packaged: false, appPath: options.appPath.toLowerCase().replaceAll("\\", "/"),
    userDataPath: options.userDataPath.toUpperCase(),
  });
  assert.equal(next.appId, first.appId);
  assert.equal(next.protocol, first.protocol);
});
