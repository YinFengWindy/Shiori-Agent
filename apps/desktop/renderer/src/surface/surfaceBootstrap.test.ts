import assert from "node:assert/strict";
import { test } from "node:test";
import { bootstrapSurfaceWindow } from "./surfaceBootstrap";

test("renders the failure card and never attempts the runtime entry when the glob fails", async () => {
  const events: string[] = [];
  await bootstrapSurfaceWindow({
    loadGlobModules: async () => { throw new Error("glob exploded"); },
    loadOwnRuntimeSurface: async () => { events.push("runtime"); },
    renderFailure: (detail) => events.push(`failure:${detail}`),
    renderSurface: () => events.push("surface"),
    onError: (scope) => events.push(`error:${scope}`),
  });
  assert.deepEqual(events, ["error:glob", "failure:插件模块加载失败"]);
});

test("still renders the surface when the runtime entry rejects", async () => {
  const events: string[] = [];
  await bootstrapSurfaceWindow({
    loadGlobModules: async () => { events.push("glob"); },
    loadOwnRuntimeSurface: async () => { throw new Error("bridge not ready"); },
    renderFailure: (detail) => events.push(`failure:${detail}`),
    renderSurface: () => events.push("surface"),
    onError: (scope) => events.push(`error:${scope}`),
  });
  assert.deepEqual(events, ["glob", "error:runtime", "surface"]);
});

test("renders the surface once both steps succeed, without reporting any error", async () => {
  const events: string[] = [];
  await bootstrapSurfaceWindow({
    loadGlobModules: async () => { events.push("glob"); },
    loadOwnRuntimeSurface: async () => { events.push("runtime"); },
    renderFailure: (detail) => events.push(`failure:${detail}`),
    renderSurface: () => events.push("surface"),
    onError: (scope) => events.push(`error:${scope}`),
  });
  assert.deepEqual(events, ["glob", "runtime", "surface"]);
});
