import { useState } from "react";
import { DeleteIcon, PlusIcon } from "../shared/icons";
import { cx, inputClass } from "../shared/styles";
import type { SettingsRoleEmoji } from "../shared/types";

type RoleEmojiSettingsProps = {
  entries: SettingsRoleEmoji[];
  onChange: (entries: SettingsRoleEmoji[]) => void;
};

/** Manages the ordered global emoji allowlist available to every role. */
export function RoleEmojiSettings({ entries, onChange }: RoleEmojiSettingsProps) {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  function updateEntry(index: number, patch: Partial<SettingsRoleEmoji>): void {
    onChange(entries.map((entry, entryIndex) => (
      entryIndex === index ? { ...entry, ...patch } : entry
    )));
  }

  function addEntry(): void {
    onChange([...entries, { name: "", value: "" }]);
  }

  function removeEntry(index: number): void {
    onChange(entries.filter((_, entryIndex) => entryIndex !== index));
  }

  function moveEntry(index: number): void {
    if (draggedIndex === null || draggedIndex === index) return;
    const next = [...entries];
    const [dragged] = next.splice(draggedIndex, 1);
    if (!dragged) return;
    next.splice(index, 0, dragged);
    onChange(next);
    setDraggedIndex(null);
  }

  return (
    <section className="grid gap-3 py-5">
      <div className="flex items-center justify-end">
        <button
          className="grid h-10 w-10 place-items-center rounded-md border border-[#D6DCE3] bg-white text-[#5B616A] transition hover:bg-[#EEF2F6] focus:outline-none"
          type="button"
          aria-label="添加 Emoji"
          title="添加 Emoji"
          onClick={addEntry}
        >
          <PlusIcon className="h-[18px] w-[18px] fill-current" />
        </button>
      </div>
      <div className="grid gap-2.5">
        {entries.map((entry, index) => (
          <div
            className="grid grid-cols-[minmax(0,1fr)_120px_40px] items-center gap-3 rounded-md border border-[#E6E9EE] bg-[#FBFBFC] p-3"
            key={`${entry.name}-${index}`}
            draggable
            onDragStart={() => setDraggedIndex(index)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => moveEntry(index)}
            onDragEnd={() => setDraggedIndex(null)}
          >
            <input
              className={cx(inputClass, "bg-white")}
              value={entry.name}
              placeholder="名称，例如 heart"
              aria-label={`Emoji ${index + 1} 名称`}
              onChange={(event) => updateEntry(index, { name: event.target.value })}
            />
            <input
              className={cx(inputClass, "bg-white text-center text-xl")}
              value={entry.value}
              placeholder="😊"
              aria-label={`Emoji ${index + 1} 字符`}
              onChange={(event) => updateEntry(index, { value: event.target.value })}
            />
            <button
              className="grid h-10 w-10 place-items-center rounded-md text-[#C16E4E] transition hover:bg-white focus:outline-none"
              type="button"
              aria-label={`删除 Emoji ${index + 1}`}
              onClick={() => removeEntry(index)}
            >
              <DeleteIcon className="h-4 w-4 fill-current" />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
