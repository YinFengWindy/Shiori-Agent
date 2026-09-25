import { Plus, X } from "@phosphor-icons/react";
import { useState } from "react";
import { appendStringListItem } from "../stringList";
import { compactPressableClass, cx } from "../styles";

type StringListInputProps = {
  items: readonly string[];
  onChange: (items: string[]) => void;
  ariaLabel: string;
  /** Surface of the entry input, owned by the host form (settings or role editor). */
  inputClassName: string;
  /** Surface of the icon-only add button, owned by the host form. */
  addButtonClassName: string;
  placeholder?: string;
  /** Shows the chips only: no remove buttons and no entry input. */
  readOnly?: boolean;
};

/**
 * Editor for a list of short strings (ids, names): each entry is a removable
 * chip; Enter or the add button appends the typed value, and Backspace in an
 * empty input removes the last chip.
 */
export function StringListInput({ items, onChange, ariaLabel, inputClassName, addButtonClassName, placeholder, readOnly = false }: StringListInputProps) {
  const [text, setText] = useState("");
  const add = () => {
    const next = appendStringListItem(items, text);
    setText("");
    if (next.length !== items.length) onChange(next);
  };
  return (
    <div className="grid gap-2" role="group" aria-label={ariaLabel}>
      {items.length > 0 ? (
        <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {items.map((item) => (
            <li key={item} className={cx("inline-flex max-w-full items-center gap-1 rounded-full bg-accent-softer py-0.5 pl-2.5 text-caption text-accent-text", readOnly ? "pr-2.5" : "pr-1")}>
              <span className="truncate font-mono">{item}</span>
              {readOnly ? null : (
                <button
                  type="button"
                  className={cx(compactPressableClass, "grid h-5 w-5 shrink-0 place-items-center rounded-full hover:bg-accent-soft")}
                  aria-label={`移除 ${item}`}
                  onClick={() => onChange(items.filter((value) => value !== item))}
                >
                  <X className="h-3 w-3" weight="bold" aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      {readOnly ? null : (
        <div className="flex items-center gap-2">
          <input
            aria-label={`输入${ariaLabel}`}
            className={cx(inputClassName, "min-w-0 flex-1")}
            value={text}
            placeholder={placeholder}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                add();
              } else if (event.key === "Backspace" && !text && items.length > 0) {
                onChange(items.slice(0, -1));
              }
            }}
            onBlur={() => { if (text.trim()) add(); }}
          />
          <button type="button" className={addButtonClassName} aria-label={`添加${ariaLabel}`} title="添加" disabled={!text.trim()} onClick={add}>
            <Plus className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </button>
        </div>
      )}
    </div>
  );
}
