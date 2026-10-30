import React, { useRef } from "react";
import { CrossfadeLayers } from "@yinfengwindy/shiori-sdk";
import { cx } from "@yinfengwindy/shiori-sdk";
import { useChatAffectionContribution } from "../plugins/affectionUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
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
  /** The role whose chat is open; the affection plugin's block reads its own data for it. */
  roleId: string;
  roleSelfView: string;
  visualsActive?: boolean;
};

/** Renders the chat status sidebar with the current mood and mapped illustration. */
export function ChatStatusSidebar({
  currentMood,
  moodUpdatedAt,
  moodScope,
  moodIllustrationUrl,
  roleId,
  roleSelfView,
  visualsActive = true,
}: ChatStatusSidebarProps) {
  const contributed = useChatAffectionContribution();
  const pluginEnabled = usePluginEnabledState();
  // Affection, relationship tags and loneliness are the plugin's own block; the
  // sidebar only mounts the slot while the plugin is on.
  const AffectionBlock = contributed && pluginEnabled(contributed.pluginId) && roleId ? contributed.Component : null;
  const shouldRenderIllustration = Boolean(moodIllustrationUrl) && visualsActive;
  const layerRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const pillRef = useRef<HTMLSpanElement | null>(null);
  const cue = useMoodChangeCue({ scope: moodScope, mood: currentMood, updatedAt: moodUpdatedAt });
  // A hidden window skips the performance; the new mood simply shows on return.
  useMoodChangeMotion({ cue: visualsActive ? cue : null, layerRef, frameRef, pillRef });
  return (
    <div
      className={cx(
        chatSidebarPanelClass,
        "chat-status-sidebar relative gap-3",
        AffectionBlock ? "grid-rows-[minmax(0,1fr)_auto_auto_auto]" : "grid-rows-[minmax(0,1fr)_auto_auto]",
      )}
    >
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
      {/* Keyed by role so a switch never shows the previous role's data while it reloads. */}
      {AffectionBlock ? <AffectionBlock key={roleId} roleId={roleId} /> : null}
      {/* Mood-change particles fly over the whole panel without catching the pointer. */}
      <div ref={layerRef} className="mood-burst-layer" aria-hidden="true" />
    </div>
  );
}
