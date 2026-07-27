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
    <nav className="flex min-w-0 items-center gap-6 overflow-x-auto" aria-label="角色详情分区">
      {tabs.map((tab) => {
        const selected = activeTab === tab.id;
        return (
          <button
            className={cx(
              "h-10 shrink-0 border-b-2 px-1 text-sm transition-colors focus:outline-none",
              selected ? "border-[#a85d38] font-medium text-[#38231a]" : "border-transparent text-[#89766d] hover:text-[#38231a]",
            )}
            key={tab.id}
            type="button"
            aria-current={selected ? "page" : undefined}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
