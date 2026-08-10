/// <reference types="node" />

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { prepareModelRegistrationRemoval } from "./modelRegistrationRemoval.js";

const originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");

afterEach(() => {
  if (originalWindowDescriptor) {
    Object.defineProperty(globalThis, "window", originalWindowDescriptor);
  } else {
    Reflect.deleteProperty(globalThis, "window");
  }
});

describe("prepareModelRegistrationRemoval", () => {
  it("returns affected role updates without persisting them", async () => {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: {
        alert: () => undefined,
        confirm: () => true,
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

    const removable = await prepareModelRegistrationRemoval(
      {
        id: "registration-1",
        provider: "openai",
        model: "gpt-agent",
        baseUrl: "",
        apiKey: "",
        effort: "none",
      },
      [
        { id: "registration-1", provider: "openai", model: "gpt-agent", baseUrl: "", apiKey: "", effort: "none" },
        { id: "registration-2", provider: "openai", model: "gpt-next", baseUrl: "", apiKey: "", effort: "high" },
      ],
    );

    assert.deepEqual(removable, [{
      roleId: "role-1",
      runtimeConfig: {
        dialogue_model_registration_id: "registration-2",
        visual_model_registration_id: "",
      },
    }]);
  });
});
