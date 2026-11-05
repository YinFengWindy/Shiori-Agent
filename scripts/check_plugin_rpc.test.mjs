import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { checkPluginRpc } from './check_plugin_rpc.mjs';

function fixture(source, extension = 'ts') {
  const directory = mkdtempSync(join(tmpdir(), 'shiori-rpc-contract-'));
  writeFileSync(join(directory, 'manifest.yaml'), 'api: 4\nid: contract_probe\nsdk: ">=4.0.0 <4.2.0"\n', 'utf8');
  writeFileSync(join(directory, 'rpc-contract.generated.json'), JSON.stringify({ plugin_id: 'contract_probe', dependencies: ['telegram', 'desktop_pet'], methods: ['read', 'write'], services: [{ service_id: 'voice', contract: 'voice.v1', methods: ['speak'] }] }), 'utf8');
  writeFileSync(join(directory, `probe.${extension}`), 'import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";\n' + source, 'utf8');
  return { directory, run: () => checkPluginRpc({ plugin: directory }), close: () => rmSync(directory, { recursive: true, force: true }) };
}

test('actual SDK calls require a finite provider name, including aliases and unions', () => {
  const f = fixture(`
export async function check(client: PluginRpcClient, method: "read" | "write", dynamic: string) {
  await client.call(method);
  const { call } = client;
  await call("typo");
  await client.call(dynamic);
}`);
  try {
    const result = f.run();
    assert.equal(result.checked, 2);
    assert.equal(result.errors.length, 2);
    assert.ok(result.errors.some((error) => error.includes('"typo" has no provider')));
    assert.ok(result.errors.some((error) => error.includes('finite string-literal type')));
  } finally { f.close(); }
});

test('background names and service references cannot pass as backend methods', () => {
  const f = fixture(`
export async function check(client: PluginRpcClient) {
  await client.handle("background.ready", async () => ({}));
  await client.background.call("background.ready");
  await client.background.call("missing");
  await client.call("background.ready");
  await client.services.call({plugin_id: "contract_probe", service_id: "voice"}, "speak");
  await client.services.call({plugin_id: "contract_probe", service_id: "other"}, "speak");
  await client.services.list("voice.v1");
  await client.services.list("missing.v1");
}`);
  try {
    const result = f.run();
    assert.equal(result.errors.length, 4);
    assert.ok(result.errors.some((error) => error.includes('background method "missing"')));
    assert.ok(result.errors.some((error) => error.includes('backend method "background.ready"')));
    assert.ok(result.errors.some((error) => error.includes('services method "speak"')));
    assert.ok(result.errors.some((error) => error.includes('service-contract method "missing.v1"')));
  } finally { f.close(); }
});

test('a peer call uses the declared dependency provider, not the caller method set', () => {
  const f = fixture(`
export async function check(client: PluginRpcClient) {
  const peer = await client.dependency("telegram");
  if (peer) { const { call } = peer; await call("bot.save"); await peer.call("read"); }
  const pet = await client.dependency("desktop_pet");
  if (pet) { await pet.background.call("voice.stop"); await pet.background.call("read"); }
  await client.dependency("undeclared");
}`);
  try {
    const result = f.run();
    assert.equal(result.errors.length, 3);
    assert.ok(result.errors.some((error) => error.includes('"read" has no provider in telegram')));
    assert.ok(result.errors.some((error) => error.includes('dependency method "undeclared"')));
    assert.ok(result.errors.some((error) => error.includes('background method "read" has no provider in desktop_pet')));
  } finally { f.close(); }
});

test('an SDK panel checks the backend methods used inside its shared hook', () => {
  const f = fixture(`
import { ManagedRuntimePanel, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
export function Settings({ client, host }: PluginSettingsSectionComponentProps) {
  return <ManagedRuntimePanel client={client} host={host} importExtensions={[]} />;
}`, 'tsx');
  try {
    const result = f.run();
    assert.ok(result.errors.some((error) => error.includes('"runtime.status" has no provider')));
    assert.ok(result.errors.some((error) => error.includes('"runtime.relocate" has no provider')));
    assert.ok(result.errors.every((error) => error.includes('useManagedRuntime.ts')));
  } finally { f.close(); }
});
