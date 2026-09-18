import { version as reactVersion } from "react";
import type { FixtureBackground } from "./contract";

/** Timer, subscription, method and surface all belong to this effect scope. */
export default {
  pluginId: "external_demo",
  async setup(ctx: FixtureBackground) {
    let ticks = 0;
    let events = 0;
    let pending = Promise.resolve();
    let persistenceError: unknown;
    const snapshot = (alive = true) => ({ version: __FIXTURE_VERSION__, ticks, events, alive, reactVersion });
    const persist = (alive = true) => { pending = pending.then(() => ctx.store.write(snapshot(alive))); return pending; };
    await ctx.rpc.handle("inspect", () => snapshot());
    await ctx.events.on("pulse", () => { events += 1; });
    const timer = setInterval(() => {
      ticks += 1;
      void persist().catch((error) => { persistenceError = error; clearInterval(timer); });
    }, 100);
    ctx.effect("fixture_resources", async () => {
      clearInterval(timer);
      try { await persist(false); }
      finally { await ctx.surfaces.destroy("probe"); }
      if (persistenceError) throw persistenceError;
    });
    await ctx.surfaces.create("probe", { body: { width: 300, height: 150 }, transparent: false, alwaysOnTop: true, skipTaskbar: false }, { x: 80, y: 80 });
    ctx.surfaces.show("probe");
    await persist();
  },
};
