import React from "react";
import { cx } from "../shared/styles";
import { chatSidebarPanelClass } from "./chatSidebarStyles";

type ChatStatusSidebarProps = {
  currentMood: string;
  moodIllustrationUrl: string;
  roleSelfView: string;
  relationshipTags: string[];
  lonelinessValue: number;
  visualsActive?: boolean;
};

/** Renders the chat status sidebar with the current mood and mapped illustration. */
export function ChatStatusSidebar({
  currentMood,
  moodIllustrationUrl,
  roleSelfView,
  relationshipTags,
  lonelinessValue,
  visualsActive = true,
}: ChatStatusSidebarProps) {
  const normalizedLoneliness = Math.max(0, Math.min(100, Number.isFinite(lonelinessValue) ? lonelinessValue : 0));
  const shouldRenderIllustration = Boolean(moodIllustrationUrl) && visualsActive;
  return (
    <div className={cx(chatSidebarPanelClass, "chat-status-sidebar grid-rows-[minmax(72px,1fr)_auto_auto_auto_auto] gap-3")}>
      {/* Absolute sizing binds the illustration to its shrinking grid row, not its intrinsic image height. */}
      <div className="relative min-h-0 rounded-md">
        {shouldRenderIllustration ? (
          <img
            className="absolute inset-0 m-auto h-full max-h-52 w-full object-contain"
            src={moodIllustrationUrl}
            alt={currentMood ? `${currentMood} status illustration` : "status illustration"}
            decoding="async"
          />
        ) : (
          <div className="absolute inset-0 m-auto grid h-full max-h-52 w-full place-items-center rounded-md bg-accent-softer text-caption text-ink-muted">
            {visualsActive ? "当前状态图还没生成" : "窗口隐藏时已暂停图片渲染"}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="text-body font-semibold text-ink-muted">当前状态</div>
        <div className="text-body font-semibold text-accent-text">
          {currentMood || "未生成"}
        </div>
      </div>
      <div className="grid gap-1 text-left">
        <div className="text-body font-semibold text-ink-muted">当下想法</div>
        {/* This sidebar intentionally uses the compact 13px body scale; its full text owns its row height. */}
        <div className="whitespace-pre-wrap break-words text-body-sm font-normal text-ink-secondary" role="region" aria-label="当下想法">
          {roleSelfView || "我还在慢慢整理自己现在对你的想法。"}
        </div>
      </div>
      {relationshipTags.length ? (
        <div className="flex flex-wrap gap-1">
          {relationshipTags.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-accent-soft px-1.5 py-0.5 text-caption text-accent-text"
            >
              {tag}
            </span>
          ))}
        </div>
      ) : (
        <div className="text-caption text-ink-muted">关系标签还在生成中</div>
      )}
      <div>
        <div className="flex items-center justify-between gap-3">
          <div className="text-body font-semibold text-ink-muted">寂寞值</div>
          <div className="text-body font-semibold tabular-nums text-ink">{Math.round(normalizedLoneliness)}</div>
        </div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-accent-soft">
          <div
            className="h-full rounded-full bg-gradient-accent-medium transition-[width] duration-300"
            style={{ width: `${normalizedLoneliness}%` }}
          />
        </div>
      </div>
    </div>
  );
}
