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

test("generic renderer bridge calls cannot invoke observation methods", () => {
  const start = ipcSource.indexOf('ipcMain.handle("desktop:invoke"');
  const end = ipcSource.indexOf('ipcMain.on("desktop:start-attachment-drag"', start + 1);
  const source = ipcSource.slice(start, end);

  assert.match(source, /request\.method\.startsWith\("observation\."\)/);
  assert.match(source, /restricted to the main process/);
});

test("pet observation controls authorize the active pet window", () => {
  const start = ipcSource.indexOf('ipcMain.handle("desktop:pet-observation-toggle"');
  const end = ipcSource.indexOf('ipcMain.on("desktop:pet-renderer-ready"', start + 1);
  const source = ipcSource.slice(start, end);

  assert.match(source, /desktop:pet-observation-request/);
  assert.match(source, /desktop:pet-observation-dismiss/);
  assert.equal(source.match(/desktopPet\.isPetWindow\(petWindow\)/g)?.length, 3);
});

test("pet renderer handshake is delegated to the active pet controller", () => {
  const start = ipcSource.indexOf('ipcMain.on("desktop:pet-renderer-ready"');
  const end = ipcSource.indexOf('ipcMain.on("desktop:pet-drag-start"', start + 1);
  const source = ipcSource.slice(start, end);

  assert.match(source, /desktopPet\.rendererReady\(BrowserWindow\.fromWebContents\(event\.sender\)\)/);
});
