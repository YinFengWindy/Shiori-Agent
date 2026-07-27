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
    <nav className="flex w-full items-center gap-1 overflow-x-auto rounded-md border border-white/40 bg-black/20 p-1.5 backdrop-blur-md" aria-label="角色详情分区">
      {tabs.map((tab) => {
        const selected = activeTab === tab.id;
        return (
          <button
            className={cx(
              "relative min-h-9 shrink-0 rounded-md px-3.5 text-sm transition-colors focus:outline-none",
              selected ? "text-[#37251d]" : "text-white/80 hover:bg-white/10 hover:text-white",
            )}
            key={tab.id}
            type="button"
            aria-current={selected ? "page" : undefined}
            onClick={() => onChange(tab.id)}
          >
            {selected ? <motion.span layoutId="role-detail-active-tab" className="absolute inset-0 rounded-md bg-[rgba(255,248,242,0.9)] shadow-[0_4px_18px_rgba(39,23,15,0.18)]" transition={{ type: "spring", stiffness: 420, damping: 32 }} /> : null}
            <span className="relative">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
