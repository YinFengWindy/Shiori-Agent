/// <reference types="node" />

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { describeModelRegistrationRemoval, planModelRegistrationRemoval } from "./modelRegistrationRemoval.js";

const originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");

afterEach(() => {
  if (originalWindowDescriptor) {
    Object.defineProperty(globalThis, "window", originalWindowDescriptor);
  } else {
    Reflect.deleteProperty(globalThis, "window");
  }
});

describe("planModelRegistrationRemoval", () => {
  it("returns affected role updates without persisting them", async () => {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: {
        miraDesktop: {
          invoke: async (request: { method: string; payload: Record<string, unknown> }) => {
            if (request.method === "roles.list") {
              return {
                payload: {
                  roles: [{
                    id: "role-1",
                    name: "Shiori",
                    runtime_config: {
                      dialogue_model_registration_id: "registration-1",
                      visual_model_registration_id: "registration-1",
                      unrelated_setting: "must remain owned by the role",
                    },
                  }],
                },
                error: null,
              };
            }
            throw new Error(`unexpected ${request.method}`);
          },
        },
      },
    });

    const plan = await planModelRegistrationRemoval(
      {
        id: "registration-1",
        provider: "openai",
        model: "gpt-agent",
        baseUrl: "",
        apiKey: "",
        effort: "none",
      },
    );

    assert.deepEqual(plan.affectedRoleNames, ["Shiori"]);
    assert.match(describeModelRegistrationRemoval(plan), /Shiori 将失去所绑定的模型/);
    assert.deepEqual(plan.updates, [{
      roleId: "role-1",
      runtimeConfig: {
        dialogue_model_registration_id: "",
        visual_model_registration_id: "",
      },
    }]);
  });

  it("fails loudly instead of confirming when roles cannot be read", async () => {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { miraDesktop: { invoke: async () => ({ payload: {}, error: { code: "bridge_exit", message: "bridge stopped" } }) } },
    });
    await assert.rejects(
      planModelRegistrationRemoval({ id: "r", provider: "openai", model: "m", baseUrl: "", apiKey: "", effort: "none" }),
      /bridge stopped/,
    );
  });
});
