/**
 * Development-only test support for plugin renderer code
 * (`@shiori/plugin-sdk/testing`, #505). Not a runtime peer: it is never part
 * of the renderer import map or the peer ABI, so production plugin code must
 * not import it. The host's own tests use the same harness.
 */
export { deferred } from "./deferred";
export { changeInputValue, mockableWindowTimers, mountTestComponent } from "./domTestHarness";
export { chooseSelectOption } from "./selectTestActions";
export { createFakeHostServices, type FakeHostServices, type FakeHostServicesOptions } from "./fakeHostServices";
export { createFakePluginClient } from "./fakePluginClient";
