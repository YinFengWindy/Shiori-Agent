/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ModelRegistrationDetails } from "./ModelRegistrationDetails.js";

describe("ModelRegistrationDetails", () => {
  it("renders navigation, deletion, and all registration fields", () => {
    const markup = renderToStaticMarkup(
      <ModelRegistrationDetails
        registration={{
          id: "registration-1",
          provider: "openai",
          model: "gpt-agent",
          baseUrl: "https://agent.example",
          apiKey: "secret",
          effort: "high",
        }}
        canDelete
        onBack={() => undefined}
        onChange={() => undefined}
        onDelete={() => undefined}
      />,
    );

    assert.match(markup, /aria-label="返回模型注册列表"/);
    assert.match(markup, /aria-label="删除模型注册"/);
    assert.match(markup, /value="openai"/);
    assert.match(markup, /value="gpt-agent"/);
    assert.match(markup, /value="https:\/\/agent\.example"/);
    assert.match(markup, /value="secret"/);
    assert.match(markup, /<select/);
  });
});
