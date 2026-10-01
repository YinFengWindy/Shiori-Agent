import assert from "node:assert/strict";
import { test } from "node:test";
import { PluginHostServicesProvider } from "@shiori/sdk";
import { createFakeHostServices, mountTestComponent } from "@shiori/sdk/testing";
import { StoryError } from "./StoryError";

test("Story error presentation delegates separate summary/detail to the shared disclosure", async () => {
  const fake = createFakeHostServices();
  const view = await mountTestComponent(<PluginHostServicesProvider services={fake.host}><StoryError message="剧情加载失败" detail="database unavailable" /></PluginHostServicesProvider>);
  try {
    assert.deepEqual(fake.uiRenders.InlineError.at(-1), { message: "剧情加载失败", detail: "database unavailable", persona: false });
  } finally { await view.cleanup(); }
});
