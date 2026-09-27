import assert from "node:assert/strict";
import { it } from "node:test";
import { initialSemanticQuery, pickOffered, sameSemanticFilters, sameSemanticQuery, semanticListParams, semanticStatusLabel } from "./roleSemanticMemory";

it("sends only the sort direction and batch, leaving unset filters out of list params", () => {
  assert.deepEqual(semanticListParams("mira", initialSemanticQuery, 1), {
    role_id: "mira", q: "", sort_order: "desc", page: 1, page_size: 20,
  });
  assert.deepEqual(semanticListParams("mira", { ...initialSemanticQuery, memory_type: "event", memory_domain: "life", status: "all", sort_order: "asc" }, 3), {
    role_id: "mira", q: "", sort_order: "asc", page: 3, page_size: 20, memory_type: "event", memory_domain: "life", status: "all",
  });
});

it("narrows a picked value to the offered set and rejects anything else", () => {
  assert.equal(pickOffered(["desc", "asc"], "asc"), "asc");
  assert.throws(() => pickOffered(["desc", "asc"], "updated_at:desc"), /unexpected option/);
});

it("compares queries by every requested field", () => {
  assert.equal(sameSemanticQuery(initialSemanticQuery, { ...initialSemanticQuery }), true);
  assert.equal(sameSemanticQuery(initialSemanticQuery, { ...initialSemanticQuery, status: "active" }), false);
  assert.equal(sameSemanticQuery(initialSemanticQuery, { ...initialSemanticQuery, q: "tea" }), false);
});

it("compares filter declarations by dimension and value", () => {
  assert.equal(sameSemanticFilters({ memory_type: ["event"] }, { memory_type: ["event"] }), true);
  assert.equal(sameSemanticFilters({ memory_type: ["event"] }, { memory_type: ["event", "turn"] }), false);
  assert.equal(sameSemanticFilters({}, { status: ["active"] }), false);
  assert.equal(sameSemanticFilters(null, {}), false);
  assert.equal(sameSemanticFilters(null, null), true);
});

it("labels known statuses and passes unknown ones through", () => {
  assert.equal(semanticStatusLabel("superseded"), "已失效");
  assert.equal(semanticStatusLabel("archived"), "archived");
});
