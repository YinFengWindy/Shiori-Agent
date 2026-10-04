import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { installedNotificationAppId, windowsNotificationIdentity } from "./windowsIdentity.js";
import { registerWindowsNotifications, repairLegacyNotificationShortcut } from "./windowsRegistration.js";

test("repairs the observed Electron shortcut collision without deleting or repointing the shortcut", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "shiori-shortcut-test-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const path = join(directory, "Electron.lnk");
  writeFileSync(path, "test shortcut", "utf8");
  const original = {
    target: "D:\\Coding\\Shiori\\node_modules\\electron\\dist\\electron.exe",
    args: "", cwd: "D:\\Coding\\Shiori\\node_modules\\electron\\dist",
    appUserModelId: installedNotificationAppId,
    toastActivatorClsid: "08485308-8AD8-48E6-99CC-1EA5C4E54862",
    icon: "C:\\Existing.ico", iconIndex: 0,
  };
  const writes: unknown[][] = [];
  repairLegacyNotificationShortcut(path, {
    readShortcutLink: () => original,
    writeShortcutLink: (path, operation, details?) => { writes.push([path, operation, details]); return true; },
  });
  assert.deepEqual(writes, [[path, "update", { ...original, appUserModelId: `${installedNotificationAppId}.dev.legacy` }]]);
  for (const unrelated of [
    { ...original, appUserModelId: "other.electron.app" },
    { ...original, target: "D:\\Shiori\\Shiori.exe" },
  ]) repairLegacyNotificationShortcut(path, {
    readShortcutLink: () => unrelated,
    writeShortcutLink: () => assert.fail("must preserve unrelated shortcut"),
  });
});

test("registration stores branding and a complete command with app and profile arguments", () => {
  const identity = windowsNotificationIdentity({
    packaged: false, appPath: "D:\\Source With Spaces\\apps\\desktop", userDataPath: "C:\\Profile With Spaces",
    executablePath: "D:\\Source With Spaces\\node_modules\\electron.exe", iconPath: "D:\\icon.png",
  });
  const protocols: unknown[][] = [];
  const metadata: unknown[] = [];
  registerWindowsNotifications({
    identity, programsPath: "Z:\\nonexistent-shiori-test-programs",
    app: { setAsDefaultProtocolClient: (...args) => { protocols.push(args); return true; } },
    shortcuts: { readShortcutLink: () => assert.fail("missing shortcut"), writeShortcutLink: () => assert.fail("missing shortcut") },
    writeMetadata: (value) => { metadata.push(value); },
  });
  assert.deepEqual(metadata, [identity]);
  assert.deepEqual(protocols, [[identity.protocol, identity.executablePath, [
    "D:\\Source With Spaces\\apps\\desktop", "--shiori-user-data-dir=C:\\Profile With Spaces",
  ]]]);
});

test("a rejected OS registration is a surfaced error instead of a broken Electron notification", () => {
  const identity = windowsNotificationIdentity({
    packaged: true, appPath: "D:\\app.asar", userDataPath: "C:\\profile", executablePath: "D:\\Shiori.exe", iconPath: "D:\\icon.png",
  });
  assert.throws(() => registerWindowsNotifications({
    identity, programsPath: "Z:\\nonexistent-shiori-test-programs",
    app: { setAsDefaultProtocolClient: () => false },
    shortcuts: { readShortcutLink: () => assert.fail(), writeShortcutLink: () => assert.fail() },
    writeMetadata: () => {},
  }), /Could not register Shiori notification activation/);
});
