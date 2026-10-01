import { underlineTabClass } from "../shared/styles";

/** The role editor's available task sections. */
export type RoleDetailTabId = "profile" | "memory" | "capabilities" | "accounts";

const tabs: Array<{ id: RoleDetailTabId; label: string }> = [
  { id: "profile", label: "资料" },
  { id: "memory", label: "记忆" },
  { id: "capabilities", label: "能力" },
  { id: "accounts", label: "账号" },
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
    <nav className="-mb-px flex min-w-0 items-center gap-6 overflow-x-auto" aria-label="角色详情分区">
      {tabs.map((tab) => {
        const selected = activeTab === tab.id;
        return (
          <button
            className={underlineTabClass(selected)}
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
