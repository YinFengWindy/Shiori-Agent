/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SaveSettingsResult } from "../../../src/bridge/shared.js";
import {
  resolveSettingsSaveFeedback,
  shouldShowSettingsFeedback,
} from "./settingsSaveState.js";

function createSaveResult(overrides: {
  healthOk?: boolean;
  healthMessage?: string;
} = {}): SaveSettingsResult {
  return {
    ok: true,
    health: {
      ok: overrides.healthOk ?? true,
      message: overrides.healthMessage ?? "ok",
    },
  };
}

describe("settingsSaveState", () => {
  it("reports an immediately saved configuration", () => {
    assert.deepEqual(resolveSettingsSaveFeedback(createSaveResult()), {
      phase: "saved",
      message: "配置已即时保存。",
    });
  });

  it("reports an unhealthy bridge as a saved result with warning text", () => {
    assert.deepEqual(resolveSettingsSaveFeedback(createSaveResult({
      healthOk: false,
      healthMessage: "offline",
    })), {
      phase: "saved",
      message: "配置已保存，但健康检查失败：offline",
    });
    assert.equal(shouldShowSettingsFeedback("saved", "saved"), true);
    assert.equal(shouldShowSettingsFeedback("saving", "saving"), false);
  });
});
