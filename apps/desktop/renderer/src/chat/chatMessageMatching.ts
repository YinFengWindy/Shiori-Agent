import type { SessionMessage } from "../shared/types";
import { normalizeSessionMediaPaths } from "./chatMedia";

function normalized(value: unknown) {
  return String(value ?? "").trim();
}

function samePayloadContext(left: SessionMessage, right: SessionMessage) {
  const leftMedia = normalizeSessionMediaPaths(left.media);
  const rightMedia = normalizeSessionMediaPaths(right.media);
  return leftMedia.length === rightMedia.length
    && leftMedia.every((path, index) => path === rightMedia[index])
    && ["reply_to_message_id", "reply_to_content", "reply_to_sender"].every(
      (key) => normalized(left.metadata?.[key]) === normalized(right.metadata?.[key]),
    );
}

/** Ranks identity evidence; conflicting persisted identities always describe distinct rows. */
export function getChatMessageMatchStrength(current: SessionMessage, incoming: SessionMessage) {
  if (current.role !== incoming.role) return 0;
  const currentId = normalized(current.id);
  const incomingId = normalized(incoming.id);
  if (currentId && incomingId && currentId !== incomingId) return 0;
  if (current.seq != null && incoming.seq != null && current.seq !== incoming.seq) return 0;
  if (currentId && currentId === incomingId) return 4;
  if (current.seq != null && current.seq === incoming.seq) return 4;
  const currentClientId = normalized(current.metadata?.client_message_id);
  const incomingClientId = normalized(incoming.metadata?.client_message_id);
  if (currentClientId && incomingClientId && currentClientId !== incomingClientId) return 0;
  if (normalized(current.render_id) && normalized(current.render_id) === normalized(incoming.render_id)) return 3;
  if (currentClientId && currentClientId === incomingClientId) return 2;
  if (currentClientId && !incomingClientId) return 0;
  // Content is evidence only when upgrading a transient row. A new local turn
  // must never borrow an earlier persisted row's identity, even with equal text.
  if (currentId || current.seq != null || (!incomingId && incoming.seq == null)) return 0;
  if (current.metadata?.proactive !== incoming.metadata?.proactive
    && (current.metadata?.proactive === true || incoming.metadata?.proactive === true)) return 0;
  const currentCallIds = new Set(toolCallIds(current));
  if (toolCallIds(incoming).some((id) => currentCallIds.has(id))) return 2;
  if (!samePayloadContext(current, incoming)) return 0;
  const content = current.content;
  const thinking = String(current.reasoning_content ?? "");
  if (!content.trim() && !thinking.trim()) return 0;
  if (current.role !== "assistant") {
    return content === incoming.content && thinking === String(incoming.reasoning_content ?? "") ? 1 : 0;
  }
  // An empty persisted reasoning_content is a legitimate outcome (proactive replies,
  // interrupted turns, providers that omit reasoning) and must not be read as a
  // conflicting identity; only a non-empty value can disprove the match.
  const incomingThinking = String(incoming.reasoning_content ?? "");
  const thinkingMatches = !incomingThinking.trim() || incomingThinking.startsWith(thinking);
  return incoming.content.startsWith(content) && thinkingMatches ? 1 : 0;
}

function toolCallIds(message: SessionMessage) {
  return message.tool_chain?.flatMap((group) => group.calls.map((call) => normalized(call.call_id)).filter(Boolean)) ?? [];
}

function identityKeys(message: SessionMessage) {
  return [
    ["id", normalized(message.id)],
    ["seq", message.seq == null ? "" : String(message.seq)],
    ["render", normalized(message.render_id)],
    ["client", normalized(message.metadata?.client_message_id)],
    ...toolCallIds(message).map((id) => ["call", id]),
  ].filter(([, value]) => value).map(([kind, value]) => JSON.stringify([message.role, kind, value]));
}

/** Indexes identity evidence once for page/snapshot reconciliation, keeping content fallback bounded to local rows. */
export function createChatMessageMatcher(messages: readonly SessionMessage[]) {
  const identities = new Map<string, number[]>();
  const transientIndices: number[] = [];
  const previousSequences: (number | undefined)[] = [];
  const nextSequences: (number | undefined)[] = [];
  const userTurnIds: string[] = [];
  const hasLaterUser: boolean[] = [];
  let userTurnId = "";
  let previousSeq: number | undefined;
  messages.forEach((message, index) => {
    if (message.role === "user") userTurnId = normalized(message.metadata?.client_message_id);
    userTurnIds[index] = userTurnId;
    previousSequences[index] = previousSeq;
    if (message.seq != null) previousSeq = message.seq;
    if (!normalized(message.id) && message.seq == null) transientIndices.push(index);
    for (const key of identityKeys(message)) {
      const indices = identities.get(key) ?? [];
      indices.push(index);
      identities.set(key, indices);
    }
  });
  let nextSeq: number | undefined;
  let laterUser = false;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    nextSequences[index] = nextSeq;
    hasLaterUser[index] = laterUser;
    if (messages[index]!.role === "user") laterUser = true;
    if (messages[index]!.seq != null) nextSeq = messages[index]!.seq;
  }
  return (incoming: SessionMessage, excluded?: ReadonlySet<number>, minimumStrength = 1) => {
    const candidates = new Set(identityKeys(incoming).flatMap((key) => identities.get(key) ?? []));
    if (minimumStrength === 1) transientIndices.forEach((index) => candidates.add(index));
    let matchedIndex = -1;
    let bestStrength = minimumStrength - 1;
    for (const index of candidates) {
      if (excluded?.has(index)) continue;
      const strength = getChatMessageMatchStrength(messages[index]!, incoming);
      if (strength <= bestStrength) continue;
      const incomingTurnId = normalized(incoming.metadata?.client_message_id);
      const sameTurn = Boolean(incomingTurnId && incomingTurnId === userTurnIds[index]);
      // A failed/interrupted trace before a later user turn cannot consume that
      // turn's reply simply because the assistant repeats a familiar prefix.
      if (strength === 1 && incoming.role === "assistant" && !sameTurn
        && (hasLaterUser[index] || (incomingTurnId && userTurnIds[index]))) continue;
      const previous = previousSequences[index];
      const next = nextSequences[index];
      const withinNeighbors = incoming.seq == null
        || (previous == null || incoming.seq > previous) && (next == null || incoming.seq < next);
      if (strength > 1 || withinNeighbors) {
        bestStrength = strength;
        matchedIndex = index;
      }
    }
    return matchedIndex;
  };
}
