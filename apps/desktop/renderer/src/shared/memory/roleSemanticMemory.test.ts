import assert from "node:assert/strict";
import { it } from "node:test";
import { initialSemanticQuery, pickOffered, semanticListParams } from "./roleSemanticMemory";

it("sends only the sort direction and leaves unset filters out of list params", () => {
  assert.deepEqual(semanticListParams("mira", initialSemanticQuery), {
    role_id: "mira", q: "", sort_order: "desc", page: 1, page_size: 20,
  });
  assert.deepEqual(semanticListParams("mira", { ...initialSemanticQuery, memory_type: "event", memory_domain: "life", status: "all", sort_order: "asc" }), {
    role_id: "mira", q: "", sort_order: "asc", page: 1, page_size: 20, memory_type: "event", memory_domain: "life", status: "all",
  });
});

it("narrows a picked value to the offered set and rejects anything else", () => {
  assert.equal(pickOffered(["desc", "asc"], "asc"), "asc");
  assert.throws(() => pickOffered(["desc", "asc"], "updated_at:desc"), /unexpected option/);
});
