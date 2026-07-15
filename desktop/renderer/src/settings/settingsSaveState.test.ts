/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SaveSettingsResult } from "../../../src/shared.js";
import {
  getSettingsFeedbackTimeoutMs,
  resolveSettingsSaveFeedback,
  shouldShowSettingsFeedback,
} from "./settingsSaveState.js";

function createSaveResult(overrides: {
  restartOk?: boolean;
  lastError?: string | null;
  healthOk?: boolean;
  healthMessage?: string;
} = {}): SaveSettingsResult {
  return {
    ok: true,
    restart: {
      ok: overrides.restartOk ?? true,
      running: overrides.restartOk ?? true,
      lastError: overrides.lastError ?? null,
    },
    health: {
      ok: overrides.healthOk ?? true,
      message: overrides.healthMessage ?? "ok",
    },
  };
}

describe("settingsSaveState", () => {
  it("reports a successful restart and health check", () => {
    assert.deepEqual(resolveSettingsSaveFeedback(createSaveResult()), {
      phase: "saved",
      message: "配置已保存，Bridge 已重启。",
    });
  });

  it("keeps restart failures visible as terminal errors", () => {
    assert.deepEqual(resolveSettingsSaveFeedback(createSaveResult({
      restartOk: false,
      lastError: "spawn failed",
    })), {
      phase: "restart-failed",
      message: "配置已保存，但 Bridge 重启失败：spawn failed",
    });
    assert.equal(getSettingsFeedbackTimeoutMs("restart-failed"), 4200);
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
