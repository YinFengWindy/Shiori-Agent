import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import { desktopPluginHostServices, type PluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { RolePetPackagesPanel as PetPackagesPanel } from "./RolePetPackagesPanel";
import type { PluginRoleAssetsComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { createPluginRpcClient, type PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

function RolePetPackagesPanel({ pickFiles = async () => [], ...props }: Omit<PluginRoleAssetsComponentProps, "host"> & { pickFiles?: PluginHostServices["pickFiles"] }) {
  return <PluginHostServicesProvider services={{ ...desktopPluginHostServices, pickFiles }}>
    <PetPackagesPanel {...props} />
  </PluginHostServicesProvider>;
}

/**
 * Ports the coverage `apps/desktop/renderer/src/roles/RolePetPackagesPanel.test.tsx`
 * had before #181-D moved this panel into the plugin, and adds the behaviour the
 * move introduced: the panel now fetches its own rows, so mounting, switching
 * role and failing are all its problem rather than the host's.
 *
 * The design-token guard from the old test is carried over deliberately — it is
 * what stops #160's restyle from being undone by a hardcoded colour here.
 */

type Call = { method: string; payload: Record<string, unknown> | undefined };

const listPayload = {
  selected_package_id: "mira-pet",
  packages: [{
    id: "mira-pet",
    display_name: "Mira Pet",
    preview_abs: "C:/workspace/mira/preview.webp",
  }],
};

function fakeClient(answers: Record<string, unknown>, calls: Call[]): PluginRpcClient {
  return {
    ...createPluginRpcClient("fixture"),
    background: { call: async <T,>() => { calls.push({ method: "background.sync", payload: undefined }); return undefined as T; } },
    call: <T,>(method: string, payload?: Record<string, unknown>) => {
      calls.push({ method, payload });
      const answer = answers[method];
      if (answer instanceof Error) return Promise.reject(answer);
      return Promise.resolve((answer ?? listPayload) as T);
    },
  };
}

/**
 * Installs the preload API the panel reaches for.
 *
 * Must run *after* `mountTestComponent`: the harness is what creates `window`,
 * so stubbing before it means writing onto nothing and the panel fails with
 * "Cannot read properties of undefined".
 */
function stubDesktopApi(overrides: Partial<Record<string, unknown>> = {}) {
  const host = globalThis as { window?: { miraDesktop?: unknown } };
  const miraDesktop = {
    localAssetUrl: (path: string) => `shiori-asset://local/${path}`,

    ...overrides,
  };
  if (!host.window) throw new Error("stubDesktopApi must run after mountTestComponent");
  host.window.miraDesktop = miraDesktop;
  return miraDesktop;
}

it("renders each package as a selectable preview card, with no hardcoded colours", async () => {
  const view = await mountTestComponent(null);
  stubDesktopApi();
  try {
    await view.render(<RolePetPackagesPanel
      roleId="mira" disabled={false} client={fakeClient({}, [])} onRoleDataChanged={() => undefined}
    />);
    await act(async () => { await Promise.resolve(); });

    const markup = view.container.innerHTML;
    assert.match(markup, /aria-pressed="true"/);
    assert.match(markup, /class="h-full w-full object-contain"/);
    assert.match(markup, /Mira Pet/);
    assert.match(markup, /border-accent/);
    // #160's restyle put every colour behind a token; a literal here would
    // survive typecheck and lint and only show up as a mismatched card.
    assert.doesNotMatch(markup, /border-primary|text-\[#8B4B4B\]/);
  } finally { await view.cleanup(); }
});

it("asks for the open role's packages, and for no role asks for nothing", async () => {
  const calls: Call[] = [];
  const view = await mountTestComponent(null);
  stubDesktopApi();
  try {
    await view.render(<RolePetPackagesPanel
      roleId="mira" disabled={false} client={fakeClient({}, calls)} onRoleDataChanged={() => undefined}
    />);
    await act(async () => { await Promise.resolve(); });
    assert.deepEqual(calls, [{ method: "pets.list", payload: { role_id: "mira" } }]);

    // No role open: guessing one would let a click act on another role's packages.
    await view.render(<RolePetPackagesPanel
      roleId="" disabled={false} client={fakeClient({}, calls)} onRoleDataChanged={() => undefined}
    />);
    await act(async () => { await Promise.resolve(); });
    assert.equal(calls.length, 1);
    assert.equal(view.container.innerHTML, "");
  } finally { await view.cleanup(); }
});

it("selecting a package tells the host to re-read the role and the pet to re-resolve", async () => {
  const calls: Call[] = [];
  let roleDataChanged = 0;
  const view = await mountTestComponent(null);
  stubDesktopApi();
  try {
    await view.render(<RolePetPackagesPanel
      roleId="mira" disabled={false}
      client={fakeClient({}, calls)}
      onRoleDataChanged={() => { roleDataChanged += 1; }}
    />);
    await act(async () => { await Promise.resolve(); });

    const card = view.container.querySelector<HTMLButtonElement>('[aria-pressed]');
    assert.ok(card);
    await act(async () => { card.click(); });
    await act(async () => { await Promise.resolve(); });

    assert.deepEqual(calls.at(-2), {
      method: "pets.select",
      payload: { role_id: "mira", package_id: "mira-pet" },
    });
    // Both are load-bearing: without the first the host's capability toggle
    // stays greyed out after a successful select; without the second the pet on
    // screen keeps rendering the old package.
    assert.equal(roleDataChanged, 1);
    assert.equal(calls.at(-1)?.method, "background.sync");
  } finally { await view.cleanup(); }
});

it("a failed refresh shows the reason and keeps the rows it already had", async () => {
  const view = await mountTestComponent(null);
  stubDesktopApi();
  try {
    await view.render(<RolePetPackagesPanel
      roleId="mira" disabled={false} client={fakeClient({}, [])} onRoleDataChanged={() => undefined}
    />);
    await act(async () => { await Promise.resolve(); });
    assert.match(view.container.innerHTML, /Mira Pet/);

    // `pets.list` is not admission-exempt, so a channel-config reload answers
    // `runtime_reloading`. Blanking the list on that would make a momentary
    // hiccup look like the user's packages had been deleted.
    await view.render(<RolePetPackagesPanel
      roleId="mira" disabled
      client={fakeClient({ "pets.list": new Error("正在更新渠道配置，请稍后重试") }, [])}
      onRoleDataChanged={() => undefined}
    />);
    await act(async () => { await Promise.resolve(); });

    assert.match(view.container.innerHTML, /正在更新渠道配置/);
    assert.match(view.container.innerHTML, /Mira Pet/);
  } finally { await view.cleanup(); }
});


it("removing a package also tells the host to re-read the role", async () => {
  const calls: Call[] = [];
  let roleDataChanged = 0;
  const view = await mountTestComponent(null);
  stubDesktopApi();
  try {
    await view.render(<RolePetPackagesPanel
      roleId="mira" disabled={false}
      client={fakeClient({ "pets.remove": { selected_package_id: null, packages: [] } }, calls)}
      onRoleDataChanged={() => { roleDataChanged += 1; }}
    />);
    await act(async () => { await Promise.resolve(); });

    const remove = view.container.querySelector<HTMLButtonElement>('[aria-label^="删除桌宠素材"]');
    assert.ok(remove);
    await act(async () => { remove.click(); });
    await act(async () => { await Promise.resolve(); });

    assert.deepEqual(calls.at(-2), {
      method: "pets.remove",
      payload: { role_id: "mira", package_id: "mira-pet" },
    });
    // Removing the selected package makes the backend clear
    // `desktop_pet_enabled` too. Without this the role form keeps a stale
    // `true` and the *next* `roles.update` is refused outright.
    assert.equal(roleDataChanged, 1);
    assert.equal(calls.at(-1)?.method, "background.sync");
  } finally { await view.cleanup(); }
});

it("a response for the previous role is discarded rather than shown under the new one", async () => {
  const view = await mountTestComponent(null);
  stubDesktopApi();
  let releaseFirst: (() => void) | null = null;
  const slowClient: PluginRpcClient = { ...createPluginRpcClient("fixture"),
    call: <T,>() => new Promise<T>((resolve) => {
      releaseFirst = () => resolve({
        selected_package_id: "old-pet",
        packages: [{ id: "old-pet", display_name: "旧角色的包", preview_abs: null }],
      } as T);
    }),
  };
  try {
    await view.render(<RolePetPackagesPanel
      roleId="mira" disabled={false} client={slowClient} onRoleDataChanged={() => undefined}
    />);
    await act(async () => { await Promise.resolve(); });

    // The user switches role before the first answer arrives. In the app the
    // panel is keyed by role so this remounts, but the component must not rely
    // on that: a late answer landing here would show one role's packages under
    // another's heading, and a click would then act on the wrong role.
    await view.render(<RolePetPackagesPanel
      roleId="other" disabled={false} client={fakeClient({}, [])} onRoleDataChanged={() => undefined}
    />);
    await act(async () => { await Promise.resolve(); });
    assert.ok(releaseFirst);
    await act(async () => { releaseFirst?.(); await Promise.resolve(); });

    assert.doesNotMatch(view.container.innerHTML, /旧角色的包/);
    assert.match(view.container.innerHTML, /Mira Pet/);
  } finally { await view.cleanup(); }
});


it("imports through the injected picker and retains the pets.import role/source contract", async () => {
  const calls: Call[] = [];
  const selected: unknown[] = [];
  let refreshed = 0;
  const view = await mountTestComponent(null);
  stubDesktopApi({ pickFiles: () => { throw new Error("must use injected services"); } });
  try {
    await view.render(<RolePetPackagesPanel roleId="mira" disabled={false} client={fakeClient({}, calls)}
      onRoleDataChanged={() => { refreshed += 1; }}
      pickFiles={async (options) => { selected.push(options); return ["/private/imports/desktop_pet-pets/selected.zip"]; }} />);
    const button = view.container.querySelector<HTMLButtonElement>('[aria-label="导入桌宠素材包"]');
    assert.ok(button);
    await act(async () => { button.click(); });
    assert.equal(selected.length, 1);
    assert.deepEqual(calls.at(-1), { method: "pets.import", payload: {
      role_id: "mira", source: "/private/imports/desktop_pet-pets/selected.zip",
    } });
    assert.equal(refreshed, 1);
  } finally { await view.cleanup(); }
});

it("cancelled import preserves packages and failed staging reports its error without calling pets.import", async () => {
  const calls: Call[] = [];
  let refreshed = 0;
  const view = await mountTestComponent(null);
  stubDesktopApi();
  try {
    const props = { roleId: "mira", disabled: false, client: fakeClient({}, calls), onRoleDataChanged: () => { refreshed += 1; } };
    await view.render(<RolePetPackagesPanel {...props} pickFiles={async () => []} />);
    const button = view.container.querySelector<HTMLButtonElement>('[aria-label="导入桌宠素材包"]');
    assert.ok(button);
    await act(async () => { button.click(); });
    assert.equal(calls.filter((call) => call.method === "pets.import").length, 0);
    assert.equal(refreshed, 0);
    assert.match(view.container.textContent ?? "", /Mira Pet/);
    await view.render(<RolePetPackagesPanel {...props} pickFiles={async () => { throw new Error("选择的文件超过大小限制"); }} />);
    const failedButton = view.container.querySelector<HTMLButtonElement>('[aria-label="导入桌宠素材包"]');
    assert.ok(failedButton);
    await act(async () => { failedButton.click(); });
    assert.match(view.container.textContent ?? "", /选择的文件超过大小限制/);
    assert.equal(calls.filter((call) => call.method === "pets.import").length, 0);
    assert.equal(failedButton.disabled, false);
  } finally { await view.cleanup(); }
});


it("a backend import failure retains the visible packages and does not refresh saved role data", async () => {
  const calls: Call[] = [];
  let refreshed = false;
  const view = await mountTestComponent(null);
  stubDesktopApi();
  try {
    await view.render(<RolePetPackagesPanel roleId="mira" disabled={false}
      client={fakeClient({ "pets.import": new Error("桌宠包缺少 spritesheet") }, calls)}
      onRoleDataChanged={() => { refreshed = true; }} pickFiles={async () => ["/private/package.zip"]} />);
    const button = view.container.querySelector<HTMLButtonElement>('[aria-label="导入桌宠素材包"]');
    assert.ok(button);
    await act(async () => { button.click(); });
    assert.match(view.container.textContent ?? "", /桌宠包缺少 spritesheet/);
    assert.match(view.container.textContent ?? "", /Mira Pet/);
    assert.equal(refreshed, false);
    assert.equal(button.disabled, false);
  } finally { await view.cleanup(); }
});
