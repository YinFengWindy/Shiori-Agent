/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ModelRegistrationList } from "./ModelRegistrationList.js";

describe("ModelRegistrationList", () => {
  it("renders compact registration previews and a labeled create action", () => {
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

    assert.match(markup, />添加模型</);
    assert.match(markup, />gpt-agent</);
    // Provider (a preset's label when it matches) and the base URL's host.
    assert.match(markup, />openai · agent\.example</);
    assert.match(markup, /思考 高/);
    assert.doesNotMatch(markup, /secret/);
    assert.doesNotMatch(markup, /<input/);
  });
});
