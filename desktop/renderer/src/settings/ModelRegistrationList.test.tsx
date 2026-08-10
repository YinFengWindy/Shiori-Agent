/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ModelRegistrationList } from "./ModelRegistrationList.js";

describe("ModelRegistrationList", () => {
  it("renders compact registration previews and an icon-only create action", () => {
    const markup = renderToStaticMarkup(
      <ModelRegistrationList
        registrations={[{
          id: "registration-1",
          provider: "openai",
          model: "gpt-agent",
          baseUrl: "https://agent.example",
          apiKey: "secret",
          effort: "high",
        }]}
        onCreate={() => undefined}
        onOpen={() => undefined}
      />,
    );

    assert.match(markup, /aria-label="新建模型注册"/);
    assert.match(markup, />gpt-agent</);
    assert.match(markup, />https:\/\/agent\.example</);
    assert.match(markup, />openai</);
    assert.doesNotMatch(markup, />新建注册</);
    assert.doesNotMatch(markup, /secret/);
    assert.doesNotMatch(markup, /<input/);
  });
});
