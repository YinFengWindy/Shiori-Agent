import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { chatSendFailureAction, chatSendFailurePersona, modelConfigurationRemedy } from "./chatSendFailure";

const modelError = (reason: string) => ({
  code: "model_configuration_required",
  message: "角色未选择对话模型，请先绑定模型",
  details: { reason },
});

describe("modelConfigurationRemedy", () => {
  it("sends role-level binding problems to the composer's model menu", () => {
    assert.equal(modelConfigurationRemedy(modelError("role_unbound")), "choose-role-model");
    assert.equal(modelConfigurationRemedy(modelError("registration_missing")), "choose-role-model");
  });

  it("sends missing or incomplete registrations to model settings", () => {
    assert.equal(modelConfigurationRemedy(modelError("no_models")), "open-model-settings");
    assert.equal(modelConfigurationRemedy(modelError("connection_incomplete")), "open-model-settings");
  });

  it("has no remedy for unrelated failures", () => {
    assert.equal(modelConfigurationRemedy({ code: "chat_busy", message: "busy" }), null);
    assert.equal(modelConfigurationRemedy({ message: "network down" }), null);
  });
});

describe("chatSendFailureAction", () => {
  it("wires the remedy to the matching navigation callback", () => {
    const calls: string[] = [];
    const remedies = {
      chooseRoleModel: () => { calls.push("menu"); },
      openModelSettings: () => { calls.push("settings"); },
    };
    const choose = chatSendFailureAction(modelError("role_unbound"), remedies);
    const settings = chatSendFailureAction(modelError("no_models"), remedies);
    assert.equal(choose?.label, "选择模型");
    assert.equal(settings?.label, "模型设置");
    choose?.onSelect();
    settings?.onSelect();
    assert.deepEqual(calls, ["menu", "settings"]);
    assert.equal(chatSendFailureAction({ message: "x" }, remedies), undefined);
  });
});

describe("chatSendFailurePersona", () => {
  it("has 吟风 ask for a model when the model configuration blocked the send, and fall back to her generic line", () => {
    assert.equal(chatSendFailurePersona(modelError("role_unbound")), "modelMissing");
    assert.equal(chatSendFailurePersona(modelError("no_models")), "modelMissing");
    assert.equal(chatSendFailurePersona({ code: "chat_busy", message: "busy" }), "generic");
  });
});
