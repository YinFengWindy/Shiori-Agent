import type { SessionMessage } from "../shared/types";

export const chatMessageVirtualOverscanPixels = 720;
export const chatMessageVirtualFallbackViewportHeight = 720;
export const chatMessageVirtualRowGap = 12;

export type ChatMessageVirtualWindow = {
  startIndex: number;
  endIndex: number;
  firstVisibleIndex: number;
  messages: SessionMessage[];
  topSpacerHeight: number;
  bottomSpacerHeight: number;
  totalHeight: number;
};

type GetVirtualChatMessageWindowArgs = {
  messages: readonly SessionMessage[];
  messageKeys: readonly string[];
  measuredHeights: ReadonlyMap<string, number>;
  scrollTop: number;
  viewportHeight: number;
  pinnedMessageIndex: number;
  overscanPixels?: number;
};

/** Returns a conservative pre-measurement height for one variable-height chat row. */
export function estimateChatMessageHeight(message: SessionMessage): number {
  const textLength = message.content.trim().length
    + String(message.reasoning_content ?? "").trim().length;
  const toolCallCount = message.tool_chain?.reduce(
    (total, group) => total + group.calls.length,
    0,
  ) ?? 0;
  const mediaCount = Array.isArray(message.media) ? message.media.length : 0;
  const base = message.role === "user" ? 76 : 108;
  return Math.max(
    base,
    Math.min(680, base + Math.ceil(textLength / 72) * 24 + toolCallCount * 46 + mediaCount * 190),
  );
}

function heightForMessage(
  message: SessionMessage,
  messageKey: string,
  measuredHeights: ReadonlyMap<string, number>,
): number {
  const measured = measuredHeights.get(messageKey);
  const contentHeight = measured != null && Number.isFinite(measured)
    ? Math.max(1, measured)
    : estimateChatMessageHeight(message);
  return contentHeight + chatMessageVirtualRowGap;
}

function firstIndexAfterOffset(offsets: readonly number[], offset: number): number {
  let low = 0;
  let high = offsets.length - 1;
  while (low < high) {
    const middle = low + Math.floor((high - low) / 2);
    if (offsets[middle + 1]! <= offset) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  // The final cumulative offset is the end of the last row, not a valid row
  // index. Keep the bottom-anchored window mounted at that boundary.
  return Math.min(low, Math.max(0, offsets.length - 2));
}

/**
 * Selects a bounded group of rows while retaining spacer heights for all omitted rows.
 * A pinned message takes precedence so search navigation can mount its DOM anchor on demand.
 */
export function getVirtualChatMessageWindow({
  messages,
  messageKeys,
  measuredHeights,
  scrollTop,
  viewportHeight,
  pinnedMessageIndex,
  overscanPixels = chatMessageVirtualOverscanPixels,
}: GetVirtualChatMessageWindowArgs): ChatMessageVirtualWindow {
  if (messages.length !== messageKeys.length) {
    throw new Error("消息虚拟窗口的消息和键数量不一致");
  }
  if (messages.length === 0) {
    return {
      startIndex: 0,
      endIndex: 0,
      firstVisibleIndex: 0,
      messages: [],
      topSpacerHeight: 0,
      bottomSpacerHeight: 0,
      totalHeight: 0,
    };
  }

  const offsets = [0];
  for (let index = 0; index < messages.length; index += 1) {
    offsets.push(
      offsets[index]! + heightForMessage(messages[index]!, messageKeys[index]!, measuredHeights),
    );
  }
  const totalHeight = offsets.at(-1) ?? 0;
  const safeScrollTop = Math.max(0, Math.min(scrollTop, totalHeight));
  const safeViewportHeight = Math.max(1, viewportHeight || chatMessageVirtualFallbackViewportHeight);
  const firstVisibleIndex = firstIndexAfterOffset(offsets, safeScrollTop);
  const visibleEnd = Math.min(totalHeight, safeScrollTop + safeViewportHeight);
  let startIndex = firstIndexAfterOffset(offsets, Math.max(0, safeScrollTop - overscanPixels));
  let endIndex = Math.min(
    messages.length,
    firstIndexAfterOffset(offsets, Math.min(totalHeight, visibleEnd + overscanPixels)) + 1,
  );

  if (pinnedMessageIndex >= 0 && (pinnedMessageIndex < startIndex || pinnedMessageIndex >= endIndex)) {
    startIndex = Math.max(0, pinnedMessageIndex - 12);
    endIndex = Math.min(messages.length, pinnedMessageIndex + 13);
  }

  return {
    startIndex,
    endIndex,
    firstVisibleIndex,
    messages: messages.slice(startIndex, endIndex),
    topSpacerHeight: offsets[startIndex] ?? 0,
    bottomSpacerHeight: totalHeight - (offsets[endIndex] ?? totalHeight),
    totalHeight,
  };
}
