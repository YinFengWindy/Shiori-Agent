import { CaretUp } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { modelEffortLabels } from "../shared/modelEffortLabels";
import { cx } from "../shared/styles";
import { ChatModelMenuPanel } from "./ChatModelMenuPanel";
import { subscribeChatModelMenuRequests } from "./chatModelMenuRequests";
import { useChatComposerPopover } from "./useChatComposerPopover";
import { useRoleModelSelection } from "./useRoleModelSelection";

type ChatModelMenuProps = {
  activeRoleId: string;
  bridgeReady: boolean;
};

/** Width of the popover; the position clamp needs it before the panel renders. */
const menuWidth = 240;

/** Owns the composer's model button and its flat model / effort popover. */
export function ChatModelMenu({ activeRoleId, bridgeReady }: ChatModelMenuProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const { registrations, selection, reload, update } = useRoleModelSelection(activeRoleId, bridgeReady);
  const menuPosition = useChatComposerPopover({
    open,
    onClose: () => setOpen(false),
    triggerRef: buttonRef,
    popoverRef: menuRef,
    width: menuWidth,
  });

  useEffect(() => {
    setOpen(false);
  }, [activeRoleId, bridgeReady]);

  // Opened on request (e.g. the "选择模型" action of a send that failed for
  // lack of a model). The selection is re-read first: the failure means the
  // cached one may already be stale.
  useEffect(() => subscribeChatModelMenuRequests(() => {
    void reload();
    setOpen(true);
  }), [reload]);

  // Keyboard users land on the current chat model (or the first row).
  useEffect(() => {
    if (!open || !menuPosition) return;
    const menu = menuRef.current;
    const current = menu?.querySelector<HTMLElement>('[aria-checked="true"]') ?? menu?.querySelector<HTMLElement>("button");
    current?.focus({ preventScroll: true });
  }, [open, menuPosition]);

  function selectModel(kind: "dialogue" | "visual", registrationId: string): void {
    setOpen(false);
    buttonRef.current?.focus();
    void update(kind, registrationId);
  }

  const chatModel = registrations.find((item) => item.id === selection?.dialogueId);
  if (!activeRoleId) return null;
  const effortLabel = chatModel && selection && selection.dialogueEffort !== "none"
    ? modelEffortLabels[selection.dialogueEffort]
    : "";

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        className={cx(
          "inline-flex h-[30px] max-w-[220px] items-center gap-1.5 rounded-md px-2 text-xs text-ink-secondary transition hover:bg-surface-soft hover:text-ink focus:outline-none disabled:opacity-40",
          open && "bg-surface-soft text-ink",
        )}
        type="button"
        aria-label="选择聊天模型"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={!bridgeReady || !selection}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="truncate">{chatModel?.model ?? "选择聊天模型"}</span>
        {effortLabel ? <span className="flex-none rounded-sm bg-accent-softer px-1 text-caption text-accent-text">{effortLabel}</span> : null}
        <CaretUp className={cx("h-3 w-3 flex-none transition-transform duration-quick", !open && "rotate-180")} weight="bold" aria-hidden="true" />
      </button>
      {open && selection && menuPosition ? createPortal(
        <div className="motion-popover-enter fixed z-50 origin-bottom-left" style={{ left: menuPosition.left, bottom: menuPosition.bottom }}>
          <ChatModelMenuPanel
            ref={menuRef}
            registrations={registrations}
            selection={selection}
            style={{ maxHeight: menuPosition.maxHeight }}
            onSelectModel={selectModel}
            onSelectEffort={(kind, effort) => void update(kind, effort)}
          />
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
