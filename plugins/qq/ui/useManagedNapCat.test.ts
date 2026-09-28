import assert from "node:assert/strict";
import { test } from "node:test";
import { managedPollInterval, type ManagedStatus } from "./useManagedNapCat";

const base: ManagedStatus = {
  preparation: { stage: "ready", percent: 100, version: "v4" },
  login: { phase: "stopped", qrcode: "", error: "" },
  connection: "offline",
  error: "",
};

test("status is read every second until it is connected or stopped, then every three", () => {
  const fast = [
    null,
    { ...base, preparation: { stage: "downloading", percent: 10, version: "v4" } },
    { ...base, login: { ...base.login, phase: "starting" }, connection: "connecting" },
    { ...base, login: { ...base.login, phase: "login_required" }, connection: "login_required" },
    // A shown QR code is read every second so a finished scan appears promptly.
    { ...base, login: { ...base.login, phase: "login_required", qrcode: "data:image/png;base64,QR" }, connection: "login_required" },
    // Scanned: logged in, the connection is still coming up.
    { ...base, login: { ...base.login, phase: "online" }, connection: "connecting" },
  ] satisfies Array<ManagedStatus | null>;
  for (const status of fast) assert.equal(managedPollInterval(status), 1000, JSON.stringify(status));
  const slow = [
    base,
    { ...base, login: { ...base.login, phase: "online" }, connection: "online" },
  ] satisfies ManagedStatus[];
  for (const status of slow) assert.equal(managedPollInterval(status), 3000, JSON.stringify(status));
});
