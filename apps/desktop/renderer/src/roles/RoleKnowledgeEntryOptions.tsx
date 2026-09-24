import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleKnowledgeEntry } from "../shared/types";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";

type RoleKnowledgeEntryOptionsProps = {
  entry: RoleKnowledgeEntry;
  onUpdate: (update: (current: RoleKnowledgeEntry) => RoleKnowledgeEntry) => void;
};

/** Edits matching switches and deterministic ordering for one knowledge entry. */
export function RoleKnowledgeEntryOptions({ entry, onUpdate }: RoleKnowledgeEntryOptionsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex items-center justify-between gap-3 text-caption text-ink-muted">
        <span>启用条目</span>
        <SettingsToggleCard compact ariaLabel="启用条目" checked={entry.enabled !== false} onChange={(enabled) => onUpdate((current) => ({ ...current, enabled }))} />
      </div>
      <div className="flex items-center justify-between gap-3 text-caption text-ink-muted">
        <span>常驻</span>
        <SettingsToggleCard compact ariaLabel="常驻" checked={entry.always_active === true} onChange={(always_active) => onUpdate((current) => ({ ...current, always_active }))} />
      </div>
      <div className="flex items-center justify-between gap-3 text-caption text-ink-muted sm:col-span-2">
        <span>区分大小写</span>
        <SettingsToggleCard compact ariaLabel="区分大小写" checked={entry.case_sensitive === true} onChange={(case_sensitive) => onUpdate((current) => ({ ...current, case_sensitive }))} />
      </div>
      <label className={roleFieldLabelClass}>
        <span>优先级</span>
        <input className={roleFieldClass} type="number" step={1} value={entry.priority ?? 0} onChange={(event) => {
          const priority = Number(event.target.value);
          if (Number.isSafeInteger(priority)) onUpdate((current) => ({ ...current, priority }));
        }} />
      </label>
      <label className={roleFieldLabelClass}>
        <span>插入顺序</span>
        <input className={roleFieldClass} type="number" step={1} value={entry.insertion_order ?? 0} onChange={(event) => {
          const insertion_order = Number(event.target.value);
          if (Number.isSafeInteger(insertion_order)) onUpdate((current) => ({ ...current, insertion_order }));
        }} />
      </label>
    </div>
  );
}
