/// <reference types="node" />

import assert from "node:assert/strict";
import { it } from "node:test";

import { stableLegacyRegistrationId } from "./settings.js";

it("matches Python UUIDv5 migration IDs", () => {
  assert.equal(
    stableLegacyRegistrationId(
      "main",
      "deepseek",
      "https://api.deepseek.com/v1",
      "deepseek-chat",
    ),
    "fbff36f7-a23b-507b-b545-a45a0c9a09d8",
  );
});
