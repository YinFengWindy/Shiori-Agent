import type { RoleChannelBinding, RoleProactiveCandidate } from "../shared/types";
import { isGroupChatType } from "./roleChatTypes";

/** One binding in the delivery editor together with whether it receives proactive messages. */
export type RoleBindingEntry = {
  binding: RoleChannelBinding;
  candidate: boolean;
};

/** Whether two references (a binding or a candidate) name the same channel session. */
export function sameSession(left: RoleProactiveCandidate, right: RoleProactiveCandidate) {
  return left.channel === right.channel && left.chat_id === right.chat_id;
}

/** Whether a binding is one of the proactive candidate sessions. */
export function isRoleProactiveCandidate(binding: RoleChannelBinding, candidates: RoleProactiveCandidate[]) {
  return candidates.some((candidate) => sameSession(binding, candidate));
}

/**
 * Whether a binding receives proactive messages by default: private chats and
 * the desktop (a private session) do, groups do not. The single source of this
 * default; it applies whenever a binding's session type is chosen.
 */
export function defaultsToProactiveCandidate(binding: RoleChannelBinding) {
  return !isGroupChatType(binding.chat_type);
}

/** Pairs each binding with its candidate flag, so binding edits can carry the flag along. */
export function roleBindingEntries(bindings: RoleChannelBinding[], candidates: RoleProactiveCandidate[]) {
  return bindings.map((binding) => ({ binding, candidate: isRoleProactiveCandidate(binding, candidates) }));
}

/** Splits edited entries back into the bindings and the candidates, the latter in binding order. */
export function splitRoleBindingEntries(entries: RoleBindingEntry[]) {
  return {
    channelBindings: entries.map((entry) => entry.binding),
    proactiveCandidates: entries
      .filter((entry) => entry.candidate)
      .map(({ binding }) => ({ channel: binding.channel, chat_id: binding.chat_id })),
  };
}

/** A new binding entry, a candidate when its session type defaults to one. */
export function createRoleBindingEntry(binding: RoleChannelBinding) {
  return { binding, candidate: defaultsToProactiveCandidate(binding) };
}

/**
 * Applies one edit to an entry's binding. Choosing another channel or session
 * type resets the candidate flag to that type's default; editing the number
 * or the blacklist keeps it.
 */
export function updateRoleBindingEntry(entry: RoleBindingEntry, update: (binding: RoleChannelBinding) => RoleChannelBinding) {
  const binding = update(entry.binding);
  const retyped = binding.channel !== entry.binding.channel || binding.chat_type !== entry.binding.chat_type;
  return { binding, candidate: retyped ? defaultsToProactiveCandidate(binding) : entry.candidate };
}

/** Checks or unchecks one binding as a candidate, keeping candidates in binding order. */
export function setRoleProactiveCandidate(
  bindings: RoleChannelBinding[],
  candidates: RoleProactiveCandidate[],
  target: RoleChannelBinding,
  checked: boolean,
) {
  return splitRoleBindingEntries(
    roleBindingEntries(bindings, candidates).map((entry) => (sameSession(entry.binding, target) ? { ...entry, candidate: checked } : entry)),
  ).proactiveCandidates;
}

/** Bindings that name a session yet, the ones the candidate list can offer. */
export function selectableProactiveBindings(bindings: RoleChannelBinding[]) {
  return bindings.filter((binding) => binding.chat_id.trim());
}

/** The checked candidates of selectable bindings, in binding order: what target selection may choose from. */
export function selectableProactiveCandidates(bindings: RoleChannelBinding[], candidates: RoleProactiveCandidate[]) {
  return splitRoleBindingEntries(roleBindingEntries(selectableProactiveBindings(bindings), candidates)).proactiveCandidates;
}

/** Whether two candidate lists name the same sessions in the same order. */
export function roleProactiveCandidatesEqual(left: RoleProactiveCandidate[], right: RoleProactiveCandidate[]) {
  return left.length === right.length && left.every((candidate, index) => sameSession(candidate, right[index]));
}
