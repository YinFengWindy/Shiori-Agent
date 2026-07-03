import type { SessionMessage } from "../shared/types";

/** Normalizes pending attachment paths so chat send logic can deduplicate repeated selections. */
export function normalizeChatAttachmentPaths(paths: string[]): string[] {
  const normalized: string[] = [];
  const seen = new Set<string>();
  for (const rawPath of paths) {
    const path = String(rawPath ?? "").trim();
    if (!path || seen.has(path)) {
      continue;
    }
    seen.add(path);
    normalized.push(path);
  }
  return normalized;
}

/** Returns whether the desktop chat composer currently has sendable user input. */
export function canSubmitChatMessage(content: string, attachments: string[]): boolean {
  return content.trim().length > 0 || normalizeChatAttachmentPaths(attachments).length > 0;
}

/** Builds the optimistic user message shown before the desktop bridge confirms the send. */
export function buildOptimisticUserChatMessage(content: string, attachments: string[]): SessionMessage {
  const normalizedContent = content.trim();
  const media = normalizeChatAttachmentPaths(attachments);
  if (media.length === 0) {
    return {
      role: "user",
      content: normalizedContent,
    };
  }
  return {
    role: "user",
    content: normalizedContent,
    media,
  };
}
