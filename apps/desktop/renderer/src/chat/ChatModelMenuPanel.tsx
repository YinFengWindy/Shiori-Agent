import { Check } from "@phosphor-icons/react";
import React from "react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelEffortOptions } from "../shared/modelEffortLabels";
import { cx } from "../shared/styles";
import { MenuItem, MenuPanel, menuLabelClass, menuSeparatorClass, moveMenuFocus } from "../shared/ui/Menu";
import type { ModelEffort, RoleModelSelection } from "./chatModelSelection";
import type { RoleModelSelectionChange } from "./useRoleModelSelection";

type ChatModelMenuPanelProps = {
  registrations: ModelRegistrationFormData[];
  selection: RoleModelSelection;
  /** A model was picked: the caller closes the menu. Effort changes keep it open. */
  onSelectModel: (kind: "dialogue" | "visual", registrationId: string) => void;
  onSelectEffort: (kind: Extract<RoleModelSelectionChange, "dialogueEffort" | "visualEffort">, effort: ModelEffort) => void;
};

/** Marks every keyboard-reachable row so arrow keys can walk them in order. */
const menuItemAttribute = "data-model-menu-item";

function EffortSegments({ label, value, onChange }: { label: string; value: ModelEffort; onChange: (effort: ModelEffort) => void }) {
  return (
    <div className="grid gap-1 px-1 pb-1">
      <span className={menuLabelClass}>{label}</span>
      <div className="grid grid-cols-4 gap-0.5 rounded-md bg-surface-soft p-0.5" role="radiogroup" aria-label={label}>
        {modelEffortOptions.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              {...{ [menuItemAttribute]: "" }}
              className={cx(
                "h-7 whitespace-nowrap rounded-md text-caption transition-colors duration-quick",
                selected ? "bg-white text-ink shadow-soft" : "text-ink-muted hover:bg-white/60 hover:text-ink-secondary",
              )}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(option.value)}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ModelRow({ label, selected, onSelect }: { label: string; selected: boolean; onSelect: () => void }) {
  return (
    <MenuItem
      {...{ [menuItemAttribute]: "" }}
      className="h-8 justify-between"
      role="menuitemradio"
      aria-checked={selected}
      selected={selected}
      onClick={onSelect}
    >
      <span className="min-w-0 truncate">{label}</span>
      {selected ? <Check className="h-3 w-3 flex-none" weight="bold" aria-hidden="true" /> : null}
    </MenuItem>
  );
}

/**
 * The flat model popover: 聊天模型 list with its 思考强度 right below it, then
 * 识图模型 (with its own strength when a separate vision model is chosen).
 * Arrow keys move through every row and segment; Home/End jump to the ends.
 */
export const ChatModelMenuPanel = React.forwardRef<HTMLDivElement, ChatModelMenuPanelProps & { style?: React.CSSProperties }>(
  function ChatModelMenuPanel({ registrations, selection, onSelectModel, onSelectEffort, style }, ref) {
    return (
      <MenuPanel
        ref={ref}
        className="scrollbar-stable grid w-[240px] content-start gap-0.5 overflow-y-auto"
        style={style}
        role="menu"
        aria-label="模型"
        data-testid="chat-model-menu"
        onKeyDown={(event) => moveMenuFocus(event, `[${menuItemAttribute}]`)}
      >
        <span className={menuLabelClass}>聊天模型</span>
        {registrations.length ? registrations.map((registration) => (
          <ModelRow
            key={registration.id}
            label={registration.model}
            selected={selection.dialogueId === registration.id}
            onSelect={() => onSelectModel("dialogue", registration.id)}
          />
        )) : <span className="px-2.5 py-2 text-caption text-ink-muted">还没有可用的模型</span>}
        {selection.dialogueId ? (
          <EffortSegments label="思考强度" value={selection.dialogueEffort} onChange={(effort) => onSelectEffort("dialogueEffort", effort)} />
        ) : null}
        <div className={menuSeparatorClass} role="separator" />
        <span className={menuLabelClass}>识图模型</span>
        <ModelRow label="沿用聊天模型" selected={!selection.visualId} onSelect={() => onSelectModel("visual", "")} />
        {registrations.map((registration) => (
          <ModelRow
            key={registration.id}
            label={registration.model}
            selected={selection.visualId === registration.id}
            onSelect={() => onSelectModel("visual", registration.id)}
          />
        ))}
        {selection.visualId ? (
          <EffortSegments label="识图思考强度" value={selection.visualEffort} onChange={(effort) => onSelectEffort("visualEffort", effort)} />
        ) : null}
      </MenuPanel>
    );
  },
);
