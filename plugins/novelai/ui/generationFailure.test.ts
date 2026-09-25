import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { BridgeError } from "../../../apps/desktop/renderer/src/shared/bridgeInvoke";
import { describeGenerationFailure, failurePersona, failureFromReadiness, scrubSecrets } from "./generationFailure";

describe("describeGenerationFailure", () => {
  it("maps the backend's stable codes to a kind, a title and whether settings fix it", () => {
    const cases: Array<[string, string, boolean]> = [
      ["novelai_not_configured", "not-configured", true],
      ["novelai_unauthorized", "unauthorized", true],
      ["novelai_quota", "quota", false],
      ["novelai_network", "network", false],
      ["novelai_upstream", "upstream", false],
      ["invalid_request", "invalid", false],
      ["plugin_unavailable", "unavailable", false],
      ["internal_error", "unknown", false],
    ];
    for (const [code, kind, opensSettings] of cases) {
      const failure = describeGenerationFailure(new BridgeError("原因", code));
      assert.equal(failure.kind, kind, code);
      assert.equal(failure.opensSettings, opensSettings, code);
      assert.ok(failure.title, code);
      assert.equal(failure.message, "原因");
    }
  });

  it("treats a non-bridge error as unknown and keeps its message", () => {
    const failure = describeGenerationFailure(new Error("boom"));
    assert.equal(failure.kind, "unknown");
    assert.equal(failure.title, "生成失败");
    assert.equal(failure.message, "boom");
  });

  it("never lets a bearer token or a NovelAI persistent token reach the UI", () => {
    const failure = describeGenerationFailure(new BridgeError("NovelAI 请求失败: HTTP 401 - Bearer pst-AbCdEf123456 rejected", "novelai_upstream"));
    assert.doesNotMatch(failure.message, /AbCdEf123456/);
    assert.equal(scrubSecrets("token=pst-abcdefgh"), "token=***");
    assert.equal(scrubSecrets("Authorization: Bearer abc.def"), "Authorization: Bearer ***");
    assert.equal(scrubSecrets("NovelAI 拒绝了当前 token（HTTP 401）"), "NovelAI 拒绝了当前 token（HTTP 401）");
  });
});

describe("failureFromReadiness", () => {
  it("reads an unset token (empty or an unexpanded env placeholder) as 未配置 with a settings action", () => {
    const failure = failureFromReadiness({ configured: false, reason: "placeholder", message: "NovelAI token 引用的环境变量 NOVELAI_TOKEN 未设置" });
    assert.equal(failure?.kind, "not-configured");
    assert.equal(failure?.title, "NovelAI 未配置");
    assert.match(failure?.message ?? "", /NOVELAI_TOKEN/);
    assert.equal(failure?.opensSettings, true);
  });

  it("has nothing to say when configured or still unknown", () => {
    assert.equal(failureFromReadiness({ configured: true, reason: "", message: "" }), null);
    assert.equal(failureFromReadiness(null), null);
  });
});

describe("failurePersona", () => {
  it("names the host persona scene for each stable backend code, and the generic line otherwise", () => {
    const cases: Array<[string, unknown]> = [
      ["novelai_not_configured", "not_configured"],
      ["novelai_unauthorized", "unauthorized"],
      ["novelai_quota", "quota"],
      ["novelai_network", "network"],
      ["novelai_upstream", "upstream"],
      ["invalid_request", true],
      ["plugin_unavailable", true],
      ["something_else", true],
    ];
    for (const [code, persona] of cases) {
      assert.equal(failurePersona(describeGenerationFailure(new BridgeError("x", code))), persona, code);
    }
  });
});
