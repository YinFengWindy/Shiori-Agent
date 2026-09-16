import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { useEffect } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { SurfaceRoot } from "./SurfaceRoot";
import { PluginSurfaceRegistry, type PluginSurfaceComponentProps, type SurfaceHandle } from "./pluginSurfaceRegistry";

const noopSurface: SurfaceHandle = {
  beginDrag() {}, endDrag() {}, setExtension() {}, setClickThrough() {},
  onPlacement() { return () => {}; }, onMessage() { return () => {}; },
  onState() { return () => {}; }, ready() {},
  async showContextMenu() { return null; }, activateMainWindow() {},
};
let errors: unknown[][] = [];
const realError = console.error;
beforeEach(() => { errors = []; console.error = (...args: unknown[]) => { errors.push(args); }; });
afterEach(() => { console.error = realError; });

function registryWith(Component: (props: PluginSurfaceComponentProps) => React.ReactNode) {
  const registry = new PluginSurfaceRegistry();
  registry.register({ slot: "desktop.surface", pluginId: "demo", Component });
  return registry;
}

test("mounts only the URL's plugin with its surface and scoped client", async () => {
  const seen: PluginSurfaceComponentProps[] = [];
  const registry = registryWith((props) => { seen.push(props); return <div>surface content</div>; });
  const view = await mountTestComponent(<SurfaceRoot search="?plugin=demo&surface=main" surface={noopSurface} registry={registry} />, { windowGlobals: { miraDesktop: { onEvent: () => () => {} } } });
  try {
    assert.equal(view.container.textContent, "surface content");
    assert.equal(seen[0].surfaceId, "main");
    assert.equal(seen[0].surface, noopSurface);
    assert.equal(typeof seen[0].client.call, "function");
    assert.deepEqual(errors, []);
  } finally { await view.cleanup(); }
});

for (const [search, detail] of [["", "窗口参数缺失"], ["?plugin=other&surface=main", "插件 other 未提供桌面窗口"]]) {
  test(`fails visibly and reports ready after committing: ${detail}`, async () => {
    let painted = false;
    let mountedOther = false;
    const surface = { ...noopSurface, ready() { painted = Boolean(document.querySelector('[role="alert"]')?.textContent?.includes(detail)); } };
    const registry = registryWith(() => { mountedOther = true; return null; });
    const view = await mountTestComponent(<SurfaceRoot search={search} surface={surface} registry={registry} />, { windowGlobals: { miraDesktop: { onEvent: () => () => {} } } });
    try {
      assert.match(view.container.textContent ?? "", /桌面窗口加载失败/);
      assert.equal(painted, true);
      assert.equal(mountedOther, false);
      assert.equal(errors.length, 1);
    } finally { await view.cleanup(); }
  });
}

for (const phase of ["render", "effect"]) {
  test(`contains a plugin ${phase} failure and reports ready with a readable card`, async () => {
    let ready = 0;
    const surface = { ...noopSurface, ready() { ready++; assert.ok(document.querySelector('[role="alert"]')); } };
    function Broken() {
      useEffect(() => { if (phase === "effect") throw new Error("mount exploded"); }, []);
      if (phase === "render") throw new Error("render exploded");
      return <div>partial mount</div>;
    }
    const view = await mountTestComponent(<SurfaceRoot search="?plugin=demo&surface=main" surface={surface} registry={registryWith(Broken)} />, { windowGlobals: { miraDesktop: { onEvent: () => () => {} } } });
    try {
      assert.match(view.container.textContent ?? "", /插件组件挂载失败/);
      assert.equal(ready, 1);
      assert.ok(errors.some((args) => String(args[0]).includes("插件组件挂载失败")));
    } finally { await view.cleanup(); }
  });
}
