import assert from "node:assert/strict";
import { test } from "node:test";
import { NotificationNavigation } from "./navigation.js";

test("clicks survive reads and renderer reloads until successful navigation acknowledges them", () => {
  const navigation = new NotificationNavigation();
  assert.equal(navigation.getPending(), null);
  navigation.select("mira");
  const target = navigation.getPending()!;
  assert.deepEqual(navigation.getPending(), target);
  assert.equal(target.roleId, "mira");
  navigation.acknowledge(target.id);
  assert.equal(navigation.getPending(), null);
});

test("older acknowledgements cannot consume a later click, even on the same role", () => {
  const navigation = new NotificationNavigation();
  navigation.select("mira");
  const first = navigation.getPending()!;
  navigation.select("mira");
  const second = navigation.getPending()!;
  assert.notEqual(first.id, second.id);
  navigation.acknowledge(first.id);
  assert.deepEqual(navigation.getPending(), second);
});
