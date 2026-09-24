import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { describePluginConfigFields, partitionPluginConfigFields, readEnvReference, readStringList } from "./jsonSchemaForm.js";

describe("describePluginConfigFields", () => {
  it("maps scalar types to dedicated field kinds and marks required fields", () => {
    const fields = describePluginConfigFields({
      type: "object",
      required: ["app_id"],
      properties: {
        app_id: { type: "string", title: "App ID" },
        max_retries: { type: "integer" },
        volume: { type: "number" },
        enabled: { type: "boolean" },
      },
    });

    assert.deepEqual(fields.map((f) => [f.key, f.kind, f.required]), [
      ["app_id", "string", true],
      ["max_retries", "integer", false],
      ["volume", "number", false],
      ["enabled", "boolean", false],
    ]);
    assert.equal(fields[0]?.label, "App ID");
  });

  it("flags secret-shaped string fields so they render masked", () => {
    const fields = describePluginConfigFields({
      properties: {
        client_secret: { type: "string" },
        access_token: { type: "string" },
        display_name: { type: "string" },
      },
    });

    assert.deepEqual(fields.map((f) => f.kind), ["secret", "secret", "string"]);
  });

  it("maps a string enum to an enum field with its options", () => {
    const fields = describePluginConfigFields({
      properties: { effort: { type: "string", enum: ["none", "low", "high"] } },
    });

    assert.equal(fields[0]?.kind, "enum");
    assert.deepEqual(fields[0]?.options, ["none", "low", "high"]);
  });

  it("unwraps an Optional[str]-shaped anyOf into its non-null member", () => {
    const fields = describePluginConfigFields({
      properties: {
        label: { anyOf: [{ type: "string" }, { type: "null" }] },
      },
    });

    assert.equal(fields[0]?.kind, "string");
  });

  it("falls back to a raw json field for arrays and unresolved refs", () => {
    const fields = describePluginConfigFields({
      properties: {
        groups: { type: "array" },
        // An unresolved `$ref` (or any other shape this module doesn't
        // model) has no recognizable `type`/`enum` at all.
        nested: {},
      },
    });

    assert.deepEqual(fields.map((f) => f.kind), ["json", "json"]);
  });

  it("labels fields with their schema title and description, not the raw key", () => {
    const [field] = describePluginConfigFields({
      properties: { timeout_seconds: { type: "integer", title: "单次操作超时", description: "越界会被拒绝", unit: "秒", minimum: 5, maximum: 120 } },
    });
    assert.equal(field?.label, "单次操作超时");
    assert.equal(field?.hint, "越界会被拒绝");
    assert.deepEqual([field?.unit, field?.min, field?.max], ["秒", 5, 120]);
  });

  it("renders a list of plain strings as a list editor, but a list of objects stays raw JSON", () => {
    const fields = describePluginConfigFields({
      properties: {
        allow_from: { type: "array", items: { type: "string" }, title: "允许的用户" },
        groups: { type: "array", items: { type: "object" } },
      },
    });
    assert.deepEqual(fields.map((f) => f.kind), ["stringList", "json"]);
    assert.deepEqual(partitionPluginConfigFields(fields).advanced.map((f) => f.key), ["groups"]);
    assert.deepEqual(partitionPluginConfigFields(fields).primary.map((f) => f.key), ["allow_from"]);
    assert.deepEqual(readStringList(["a", 3, "b"]), ["a", "b"]);
    assert.deepEqual(readStringList(null), []);
  });

  it("masks pydantic SecretStr fields and api-key names", () => {
    const fields = describePluginConfigFields({
      properties: {
        credential: { type: "string", format: "password", writeOnly: true },
        api_key: { type: "string" },
        hotkey: { type: "string" },
      },
    });
    assert.deepEqual(fields.map((f) => f.kind), ["secret", "secret", "string"]);
  });

  it("recognizes a bare ${NAME} environment reference, and nothing else", () => {
    assert.equal(readEnvReference("${NOVELAI_TOKEN}"), "NOVELAI_TOKEN");
    assert.equal(readEnvReference(" ${A_1} "), "A_1");
    assert.equal(readEnvReference("pst-${NOVELAI_TOKEN}"), null);
    assert.equal(readEnvReference("pst-abc"), null);
    assert.equal(readEnvReference(3), null);
  });
});
