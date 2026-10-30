import React from "react";
import { ChatStatusSidebar } from "./ChatStatusSidebar";
import { RoleTasksPanel } from "./RoleTasksPanel";
import { toFileUrl } from "../shared/format";
import type { RoleTask } from "../shared/types";
import { chatSidebarPanelClass } from "./chatSidebarStyles";

export type ChatSidebarMode = "status" | "images" | "tasks";

type ChatRightSidebarProps = {
  canGoToNextImage: boolean;
  canGoToPreviousImage: boolean;
  currentMood: string;
  imagePath: string;
  mode: ChatSidebarMode;
  moodIllustrationUrl: string;
  moodUpdatedAt: string;
  moodScope: string;
  renderHeavyVisuals: boolean;
  /** The open role; the affection plugin reads its own sidebar data for it. */
  roleId: string;
  roleSelfView: string;
  tasks: RoleTask[];
  taskError: string;
  cancellingTaskId: string;
  onClearTaskError: () => void;
  onCancelTask: (taskId: string) => Promise<void>;
  onGoToNextImage: () => void;
  onGoToPreviousImage: () => void;
  onOpenImageLightbox: () => void;
};

/** Renders the active status, task, or image panel in the chat right sidebar. */
export const ChatRightSidebar = React.memo(function ChatRightSidebar({
  canGoToNextImage,
  canGoToPreviousImage,
  currentMood,
  imagePath,
  mode,
  moodIllustrationUrl,
  moodUpdatedAt,
  moodScope,
  renderHeavyVisuals,
  roleId,
  roleSelfView,
  tasks,
  taskError,
  cancellingTaskId,
  onClearTaskError,
  onCancelTask,
  onGoToNextImage,
  onGoToPreviousImage,
  onOpenImageLightbox,
}: ChatRightSidebarProps) {
  const navButtonClass =
    "pointer-events-auto grid h-9 w-9 place-items-center rounded-md border border-line-soft bg-white/75 text-ink-secondary shadow-soft transition-colors hover:border-line hover:bg-white hover:text-ink focus:outline-none focus:ring-0 disabled:cursor-default disabled:opacity-40";
  if (mode === "status") {
    return (
      <ChatStatusSidebar
        currentMood={currentMood}
        moodIllustrationUrl={moodIllustrationUrl}
        moodUpdatedAt={moodUpdatedAt}
        moodScope={moodScope}
        roleId={roleId}
        roleSelfView={roleSelfView}
        visualsActive={renderHeavyVisuals}
      />
    );
  }
  if (mode === "tasks") {
    return (
      // Keyed by role: a switch drops the panel's view, the plugin block's included.
      <RoleTasksPanel
        key={roleId}
        roleId={roleId}
        tasks={tasks}
        cancellingTaskId={cancellingTaskId}
        error={taskError}
        onClearError={onClearTaskError}
        onCancel={onCancelTask}
      />
    );
  }
  return (
    <div className={chatSidebarPanelClass}>
      <div className="relative grid h-full min-h-0 place-items-center overflow-hidden rounded-md">
        <div className="pointer-events-none absolute inset-y-0 left-0 z-[2] flex items-center pl-3">
          <button className={navButtonClass} type="button" aria-label="查看上一张聊天图片" onClick={onGoToPreviousImage} disabled={!canGoToPreviousImage}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m15 18-6-6 6-6" />
            </svg>
          </button>
        </div>
        {imagePath && renderHeavyVisuals ? (
          <button className="grid h-full w-full place-items-center border-0 bg-transparent p-0" type="button" aria-label="放大查看当前聊天图片" onClick={onOpenImageLightbox}>
            <img className="max-h-full max-w-full object-contain" src={toFileUrl(imagePath)} alt="selected message image" decoding="async" />
          </button>
        ) : (
          <div className="grid gap-2 px-6 text-center">
            <div className="mx-auto h-10 w-10 rounded-md bg-white/70" />
            <div className="text-[12px] text-ink-muted">当前聊天里出现的图片会显示在这里</div>
          </div>
        )}
        <div className="pointer-events-none absolute inset-y-0 right-0 z-[2] flex items-center pr-3">
          <button className={navButtonClass} type="button" aria-label="查看下一张聊天图片" onClick={onGoToNextImage} disabled={!canGoToNextImage}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m9 18 6-6-6-6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
});
