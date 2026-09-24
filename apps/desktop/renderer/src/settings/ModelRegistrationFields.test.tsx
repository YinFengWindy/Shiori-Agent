import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import type { BridgeRequest, ModelRegistrationFormData } from "../../../src/bridge/shared";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { chooseSelectOption } from "../shared/testing/selectTestActions";

const initial: ModelRegistrationFormData = { id: "test", provider: "openai", model: "test-model", baseUrl: "https://example.test", apiKey: "key", effort: "none" };

async function mountFields(invoke: (request: Omit<BridgeRequest, "id">) => Promise<unknown> = async () => ({}), onConnectionTested?: (outcome: unknown) => void) {
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: { invoke } } });
  const { ModelRegistrationFields } = await import("./ModelRegistrationFields");
  const state = { registration: initial };
  const render = () => view.render(<ModelRegistrationFields compact onConnectionTested={onConnectionTested} registration={state.registration} onChange={(mutate) => { state.registration = mutate(state.registration); void render(); }} />);
  await render();
  return { view, state };
}

function button(label: string) {
  const found = Array.from(document.querySelectorAll("button")).find((item) => item.textContent === label);
  assert.ok(found, `Missing button: ${label}`);
  return found;
}

it("ModelRegistrationFields changes effort with Chinese labels while preserving the connection", async () => {
  const { view, state } = await mountFields();
  try {
    await chooseSelectOption("思考强度", "最高");
    assert.deepEqual(state.registration, { ...initial, effort: "max" });
  } finally { await view.cleanup(); }
});

it("ModelRegistrationFields fills a preset and hides the free-text provider until custom is chosen", async () => {
  const { view, state } = await mountFields();
  try {
    assert.ok(document.querySelector('[aria-label="服务商标识"]'));
    await chooseSelectOption("服务商", "DeepSeek");
    assert.deepEqual(state.registration, { ...initial, provider: "deepseek", baseUrl: "https://api.deepseek.com" });
    assert.equal(document.querySelector('[aria-label="服务商标识"]'), null);
    await chooseSelectOption("服务商", "自定义");
    assert.ok(document.querySelector('[aria-label="服务商标识"]'));
    assert.equal(state.registration.baseUrl, "https://api.deepseek.com");
  } finally { await view.cleanup(); }
});

it("ModelRegistrationFields probes the draft and shows the scrubbed failure inline", async () => {
  const requests: Array<Omit<BridgeRequest, "id">> = [];
  const outcomes: unknown[] = [];
  const { view } = await mountFields(async (request) => {
    requests.push(request);
    return { id: "1", type: "response", method: request.method, payload: { ok: false, message: "AuthenticationError: 401" }, error: null };
  }, (outcome) => outcomes.push(outcome));
  try {
    await act(async () => button("测试连接").click());
    assert.equal(requests[0]?.method, "models.test");
    assert.match(document.querySelector('[role="status"]')?.textContent ?? "", /AuthenticationError: 401/);
    // The first-run guide hears the finished probe to make 吟风 react.
    assert.deepEqual(outcomes, [{ status: "failure", message: "AuthenticationError: 401" }]);
  } finally { await view.cleanup(); }
});
