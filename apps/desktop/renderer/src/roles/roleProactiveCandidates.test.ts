import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleChannelBinding } from "../shared/types";
import {
  createRoleBindingEntry,
  defaultsToProactiveCandidate,
  roleBindingEntries,
  roleProactiveCandidatesEqual,
  selectableProactiveCandidates,
  setRoleProactiveCandidate,
  splitRoleBindingEntries,
  updateRoleBindingEntry,
} from "./roleProactiveCandidates";

const desktop: RoleChannelBinding = { channel: "desktop", chat_id: "role:mira", chat_type: "private", blocked_senders: [] };
const qqPrivate: RoleChannelBinding = { channel: "qq", chat_id: "10001", chat_type: "private", blocked_senders: [] };
const qqGroup: RoleChannelBinding = { channel: "qq", chat_id: "gqq:7", chat_type: "group", blocked_senders: [] };

describe("roleProactiveCandidates", () => {
  it("defaults private and desktop sessions into the candidates but not groups", () => {
    assert.equal(defaultsToProactiveCandidate(desktop), true);
    assert.equal(defaultsToProactiveCandidate(qqPrivate), true);
    assert.equal(defaultsToProactiveCandidate(qqGroup), false);
    assert.deepEqual(createRoleBindingEntry(qqGroup), { binding: qqGroup, candidate: false });
  });

  it("carries a candidate flag through number edits and removals", () => {
    const entries = roleBindingEntries([qqPrivate, qqGroup], [{ channel: "qq", chat_id: "10001" }]);
    const renamed = entries.map((entry, index) => (index === 0 ? updateRoleBindingEntry(entry, (binding) => ({ ...binding, chat_id: "10002" })) : entry));

    assert.deepEqual(splitRoleBindingEntries(renamed).proactiveCandidates, [{ channel: "qq", chat_id: "10002" }]);
    assert.deepEqual(splitRoleBindingEntries(renamed.slice(1)), { channelBindings: [qqGroup], proactiveCandidates: [] });
  });

  it("resets the flag to the new session type's default when the type changes", () => {
    const [entry] = roleBindingEntries([qqPrivate], [{ channel: "qq", chat_id: "10001" }]);
    const group = updateRoleBindingEntry(entry, (binding) => ({ ...binding, chat_type: "group", chat_id: "gqq:10001" }));
    const privateAgain = updateRoleBindingEntry({ ...group, candidate: false }, (binding) => ({ ...binding, chat_type: "private", chat_id: "10001" }));

    assert.equal(group.candidate, false);
    assert.equal(privateAgain.candidate, true);
  });

  it("toggles one candidate and keeps binding order", () => {
    const bindings = [desktop, qqPrivate, qqGroup];
    const withGroup = setRoleProactiveCandidate(bindings, [{ channel: "qq", chat_id: "10001" }], qqGroup, true);
    const withDesktop = setRoleProactiveCandidate(bindings, withGroup, desktop, true);

    assert.deepEqual(withDesktop, [
      { channel: "desktop", chat_id: "role:mira" },
      { channel: "qq", chat_id: "10001" },
      { channel: "qq", chat_id: "gqq:7" },
    ]);
    assert.deepEqual(setRoleProactiveCandidate(bindings, withDesktop, qqPrivate, false), [
      { channel: "desktop", chat_id: "role:mira" },
      { channel: "qq", chat_id: "gqq:7" },
    ]);
  });

  it("offers only bindings that name a session to target selection", () => {
    const unnamed: RoleChannelBinding = { ...qqPrivate, chat_id: " " };

    assert.deepEqual(
      selectableProactiveCandidates([unnamed, qqGroup], [{ channel: "qq", chat_id: " " }, { channel: "qq", chat_id: "gqq:7" }]),
      [{ channel: "qq", chat_id: "gqq:7" }],
    );
  });

  it("compares candidate lists by session and order", () => {
    const first = { channel: "qq", chat_id: "10001" };
    const second = { channel: "desktop", chat_id: "role:mira" };

    assert.equal(roleProactiveCandidatesEqual([first, second], [{ ...first }, { ...second }]), true);
    assert.equal(roleProactiveCandidatesEqual([first, second], [second, first]), false);
    assert.equal(roleProactiveCandidatesEqual([first], []), false);
  });
});
