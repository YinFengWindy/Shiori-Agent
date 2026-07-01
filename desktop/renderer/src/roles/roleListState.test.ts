/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { reconcileRoles } from "./roleListState";
import type { RoleRecord } from "../shared/types";

function createRole(overrides: Partial<RoleRecord> & Pick<RoleRecord, "id" | "name">): RoleRecord {
  return {
    id: overrides.id,
    name: overrides.name,
    description: overrides.description ?? "",
    system_prompt: overrides.system_prompt ?? "",
    runtime_config: overrides.runtime_config ?? {},
    avatar: overrides.avatar ?? null,
    avatar_abs: overrides.avatar_abs ?? null,
    featured_image: overrides.featured_image ?? null,
    featured_image_abs: overrides.featured_image_abs ?? null,
    illustrations: overrides.illustrations ?? [],
    illustrations_abs: overrides.illustrations_abs ?? [],
    created_at: overrides.created_at ?? "2026-06-29T12:00:00+08:00",
    updated_at: overrides.updated_at ?? "2026-06-29T12:00:00+08:00",
  };
}

describe("reconcileRoles", () => {
  it("drops roles that are missing from the latest bridge payload", () => {
    const current = [
      createRole({ id: "ghost-role", name: "Ghost Role" }),
      createRole({ id: "live-role", name: "Live Role" }),
    ];
    const incoming = [
      createRole({ id: "live-role", name: "Live Role" }),
    ];

    assert.deepEqual(reconcileRoles(current, incoming), incoming);
  });

  it("keeps the newer record when the same role exists in both lists", () => {
    const current = [
      createRole({
        id: "role-1",
        name: "Current Role",
        updated_at: "2026-06-29T12:05:00+08:00",
      }),
    ];
    const incoming = [
      createRole({
        id: "role-1",
        name: "Incoming Role",
        updated_at: "2026-06-29T12:10:00+08:00",
      }),
    ];

    assert.deepEqual(reconcileRoles(current, incoming), incoming);
  });

  it("preserves the current record when it is newer than the incoming one", () => {
    const current = [
      createRole({
        id: "role-1",
        name: "Current Role",
        updated_at: "2026-06-29T12:10:00+08:00",
      }),
    ];
    const incoming = [
      createRole({
        id: "role-1",
        name: "Incoming Role",
        updated_at: "2026-06-29T12:05:00+08:00",
      }),
    ];

    assert.deepEqual(reconcileRoles(current, incoming), current);
  });
});
