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
    <div className={cx(chatSidebarPanelClass, "grid-rows-[minmax(0,1fr)_auto_auto_auto_auto] gap-3")}>
      <div className="grid min-h-0 place-items-center overflow-hidden rounded-md border border-[#E1E7EF] bg-white/45 p-3">
        {shouldRenderIllustration ? (
          <img
            className="max-h-full max-w-full object-contain"
            src={moodIllustrationUrl}
            alt={currentMood ? `${currentMood} status illustration` : "status illustration"}
            decoding="async"
          />
        ) : (
          <div className="grid h-full w-full place-items-center rounded-md bg-[#EEF2F6] text-[12px] text-[#98A2B3]">
            {visualsActive ? "当前状态图还没生成" : "窗口隐藏时已暂停图片渲染"}
          </div>
        )}
      </div>
      <div className="text-center">
        <div className="text-[11px] uppercase tracking-[0.16em] text-[#7A8593]">当前状态</div>
        <div className="mt-1 text-sm font-semibold text-[#1F2937]">
          {currentMood || "未生成"}
        </div>
      </div>
      <div className="rounded-md border border-[#E1E7EF] bg-white/75 px-3 py-3 text-left">
        <div className="text-[11px] uppercase tracking-[0.16em] text-[#7A8593]">当下想法</div>
        <div className="mt-2 text-[13px] leading-6 text-[#334155]">
          {roleSelfView || "我还在慢慢整理自己现在对你的想法。"}
        </div>
      </div>
      {relationshipTags.length ? (
        <div className="flex flex-wrap gap-2">
          {relationshipTags.map((tag) => (
            <span
              key={tag}
              className="rounded-md border border-[#D9E1EB] bg-white/75 px-2.5 py-1 text-[11px] leading-none text-[#556070]"
            >
              {tag}
            </span>
          ))}
        </div>
      ) : (
        <div className="text-[11px] text-[#8A94A3]">关系标签还在生成中</div>
      )}
      <div className="rounded-md border border-[#E1E7EF] bg-white/75 px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[#7A8593]">寂寞值</div>
          <div className="text-sm font-semibold text-[#1F2937]">{Math.round(normalizedLoneliness)}</div>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#E6EBF2]">
          <div
            className="h-full rounded-full bg-[linear-gradient(90deg,#A6B8D6_0%,#65758E_100%)] transition-[width] duration-300"
            style={{ width: `${normalizedLoneliness}%` }}
          />
        </div>
      </div>
    </div>
  );
}
