/**
 * Development-only test support for plugin renderer code
 * (`@shiori/sdk/testing`, #505). Not a runtime peer: it is never part
 * of the renderer import map or the peer ABI, so production plugin code must
 * not import it. The host's own tests use the same harness.
 */
export { deferred } from "./deferred";
export { changeInputValue, mockableWindowTimers, mountTestComponent, type MountTestComponentOptions } from "./domTestHarness";
export { chooseSelectOption } from "./selectTestActions";
export {
  createFakeHostServices,
  type FakeHostCall,
  type FakeHostFeedback,
  type FakeHostServices,
  type FakeHostServicesOptions,
} from "./fakeHostServices";
export type { FakeHostUiRenders } from "./fakeHostUi";
export { createFakePluginClient } from "./fakePluginClient";
