import { ArrowClockwise } from "@phosphor-icons/react";
import { cx, iconButtonClass, underlineTabClass } from "../shared/styles";
import { memoryDocumentTabs, type MemoryTab } from "./memoryDocuments";

type MemoryNavProps = {
  tab: MemoryTab;
  onTab: (tab: MemoryTab) => void;
  onRefresh: () => void;
};

function TabButton({ selected, label, onSelect }: { selected: boolean; label: string; onSelect: () => void }) {
  return <button type="button" role="tab" aria-selected={selected} onClick={onSelect} className={underlineTabClass(selected)}>
    {label}
  </button>;
}

/** The page's single navigation row: timeline, a divider, the five documents, and refresh at the end. */
export function MemoryNav({ tab, onTab, onRefresh }: MemoryNavProps) {
  return <div className="flex items-center gap-3 border-b border-line-soft">
    <div role="tablist" aria-label="记忆视图" className="-mb-px flex min-w-0 flex-1 items-center gap-6 overflow-x-auto">
      <TabButton selected={tab === "timeline"} label="时间线" onSelect={() => onTab("timeline")} />
      <span aria-hidden="true" className="h-4 w-px shrink-0 bg-line" data-testid="memory-nav-divider" />
      {memoryDocumentTabs.map((item) => (
        <TabButton key={item.name} selected={tab === item.name} label={item.label} onSelect={() => onTab(item.name)} />
      ))}
    </div>
    <button className={cx(iconButtonClass, "mb-1")} type="button" onClick={onRefresh} aria-label="刷新记忆" title="刷新记忆">
      <ArrowClockwise className="h-4 w-4" aria-hidden="true" />
    </button>
  </div>;
}
