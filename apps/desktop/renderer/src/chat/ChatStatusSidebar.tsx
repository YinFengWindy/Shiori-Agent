import React, { useRef } from "react";
import { CrossfadeLayers } from "../shared/CrossfadeLayers";
import { cx } from "../shared/styles";
import { chatSidebarPanelClass } from "./chatSidebarStyles";
import { moodTone } from "./moodTone";
import { useMoodChangeCue } from "./useMoodChangeCue";
import { useMoodChangeMotion } from "./useMoodChangeMotion";

type ChatStatusSidebarProps = {
  currentMood: string;
  /** The session's `current_mood_updated_at`; gates the mood-change performance. */
  moodUpdatedAt: string;
  /** Role + session the mood belongs to; changing it (a role switch) never performs. */
  moodScope: string;
  moodIllustrationUrl: string;
  roleSelfView: string;
  relationshipTags: string[];
  lonelinessValue: number;
  visualsActive?: boolean;
};

/** Renders the chat status sidebar with the current mood and mapped illustration. */
export function ChatStatusSidebar({
  currentMood,
  moodUpdatedAt,
  moodScope,
  moodIllustrationUrl,
  roleSelfView,
  relationshipTags,
  lonelinessValue,
  visualsActive = true,
}: ChatStatusSidebarProps) {
  const normalizedLoneliness = Math.max(0, Math.min(100, Number.isFinite(lonelinessValue) ? lonelinessValue : 0));
  const shouldRenderIllustration = Boolean(moodIllustrationUrl) && visualsActive;
  const layerRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const pillRef = useRef<HTMLSpanElement | null>(null);
  const cue = useMoodChangeCue({ scope: moodScope, mood: currentMood, updatedAt: moodUpdatedAt });
  // A hidden window skips the performance; the new mood simply shows on return.
  useMoodChangeMotion({ cue: visualsActive ? cue : null, layerRef, frameRef, pillRef });
  return (
    <div className={cx(chatSidebarPanelClass, "chat-status-sidebar relative grid-rows-[minmax(0,1fr)_auto_auto_auto_auto] gap-3")}>
      {/* The illustration may shrink to zero; only its own pixels are clipped so text and controls take priority. */}
      <div ref={frameRef} className="chat-status-illustration-frame relative min-h-0 overflow-hidden rounded-md">
        {shouldRenderIllustration ? (
          // A mood change brings the new portrait in with a gentle scale and blur; a role switch swaps it outright.
          <CrossfadeLayers
            value={moodIllustrationUrl}
            variant="focus"
            resetKey={moodScope}
            render={(url) => (
              <img
                className="chat-status-illustration-content absolute inset-0 m-auto h-full max-h-52 w-full object-contain"
                src={url}
                alt={currentMood ? `${currentMood}状态立绘` : "状态立绘"}
                decoding="async"
              />
            )}
          />
        ) : (
          <div className="chat-status-illustration-content absolute inset-0 m-auto grid h-full max-h-52 w-full place-items-center rounded-md bg-accent-softer text-caption text-ink-muted">
            {visualsActive ? "当前状态图还没生成" : "窗口隐藏时已暂停图片渲染"}
          </div>
        )}
      </div>
      {/* Leave room for the sidebar toggle when the illustration row collapses completely. */}
      <div className="flex items-center justify-between gap-3 pr-8">
        <div className="text-body font-semibold text-ink-muted">当前状态</div>
        {currentMood ? (
          <span ref={pillRef} className="mood-pill" data-mood-tone={moodTone(currentMood)} data-testid="chat-mood-pill">
            <span className="mood-pill-dot" aria-hidden="true" />
            {currentMood}
          </span>
        ) : (
          <div className="text-body font-semibold text-ink-muted">未生成</div>
        )}
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
      {/* Mood-change particles fly over the whole panel without catching the pointer. */}
      <div ref={layerRef} className="mood-burst-layer" aria-hidden="true" />
    </div>
  );
}
