import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
let CustomMoodForm: typeof import("./CustomMoodForm").CustomMoodForm;
before(async () => { const view = await mountTestComponent(null); ({ CustomMoodForm } = await import("./CustomMoodForm")); await view.cleanup(); });

test("a valid name goes straight to the import; only a successful import clears it", async () => {
  const { host } = createFakeHostServices();
  const imports: string[] = []; let succeed = false;
  const render = (importing: boolean) => <PluginHostServicesProvider services={host}>
    <CustomMoodForm existing={["开心", "生气"]} disabled={false} importing={importing} onImport={async (name) => { imports.push(name); return succeed; }} />
  </PluginHostServicesProvider>;
  const view = await mountTestComponent(render(false));
  const input = () => view.container.querySelector<HTMLInputElement>('[aria-label="情绪名称"]')!;
  const add = () => act(async () => view.container.querySelector<HTMLButtonElement>("button")!.click());
  try {
    await changeInputValue(input(), "生气");
    await add();
    assert.deepEqual(imports, [], "a name with its own row is refused before any picker");
    assert.match(view.container.textContent ?? "", /此情绪已存在/);

    await changeInputValue(input(), " 害羞 ");
    await add();
    assert.deepEqual(imports, ["害羞"]);
    assert.equal(input().value, " 害羞 ", "a cancelled import keeps the typed name");
    assert.doesNotMatch(view.container.textContent ?? "", /此情绪已存在/);

    succeed = true;
    await act(async () => input().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    assert.deepEqual(imports, ["害羞", "害羞"]);
    assert.equal(input().value, "");

    await view.render(render(true));
    assert.equal(view.container.querySelector("button")!.textContent, "导入中…");
  } finally { await view.cleanup(); }
});
