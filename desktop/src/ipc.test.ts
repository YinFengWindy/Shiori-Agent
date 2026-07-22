import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const ipcSource = await readFile(new URL("./ipc.ts", import.meta.url), "utf-8");

function handlerSource(channel: string, nextChannel: string): string {
  const start = ipcSource.indexOf(`ipcMain.handle("${channel}"`);
  const end = ipcSource.indexOf(`ipcMain.handle("${nextChannel}"`, start + 1);
  assert.notEqual(start, -1, `${channel} handler must exist`);
  assert.notEqual(end, -1, `${nextChannel} handler must follow ${channel}`);
  return ipcSource.slice(start, end);
}

test("window controls target the BrowserWindow that sent the IPC request", () => {
  const source = handlerSource("desktop:window-control", "desktop:window-state");

  assert.match(source, /BrowserWindow\.fromWebContents\(event\.sender\)/);
  assert.doesNotMatch(source, /BrowserWindow\.getAllWindows\(\)/);
});

test("window state is read from the BrowserWindow that sent the IPC request", () => {
  const source = handlerSource("desktop:window-state", "desktop:pick-images");

  assert.match(source, /BrowserWindow\.fromWebContents\(event\.sender\)/);
  assert.doesNotMatch(source, /BrowserWindow\.getAllWindows\(\)/);
});
