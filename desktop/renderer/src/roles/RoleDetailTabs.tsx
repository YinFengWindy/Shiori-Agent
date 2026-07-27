import { motion } from "motion/react";
import { cx } from "../shared/styles";

export type RoleDetailTabId = "profile" | "capabilities" | "delivery";

const tabs: Array<{ id: RoleDetailTabId; label: string }> = [
  { id: "profile", label: "资料" },
  { id: "capabilities", label: "能力" },
  { id: "delivery", label: "渠道与主动推送" },
];

/** Renders the role-editor's task-focused navigation without adding another sidebar. */
export function RoleDetailTabs({
  activeTab,
  onChange,
}: {
  activeTab: RoleDetailTabId;
  onChange: (tab: RoleDetailTabId) => void;
}) {
  return (
    <nav className="flex w-full items-center gap-1 overflow-x-auto rounded-md bg-[#f4ebe5] p-1" aria-label="角色详情分区">
      {tabs.map((tab) => {
        const selected = activeTab === tab.id;
        return (
          <button
            className={cx(
              "relative min-h-9 shrink-0 rounded-md px-3.5 text-sm transition-colors focus:outline-none",
              selected ? "text-[#38231a]" : "text-[#76665e] hover:bg-white/65 hover:text-[#38231a]",
            )}
            key={tab.id}
            type="button"
            aria-current={selected ? "page" : undefined}
            onClick={() => onChange(tab.id)}
          >
            {selected ? <motion.span layoutId="role-detail-active-tab" className="absolute inset-0 rounded-md bg-white shadow-[0_1px_5px_rgba(77,44,29,0.12)]" transition={{ type: "spring", stiffness: 420, damping: 32 }} /> : null}
            <span className="relative">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
