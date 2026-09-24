import { useEffect, useState } from "react";
import { FolderSimplePlus } from "@phosphor-icons/react";
import type { RoleAssetCategory, RoleRecord } from "../shared/types";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import {
  deleteRoleAssetCategory,
  getRoleAssetCategories,
  groupRoleAssetsByCategory,
  moveRoleAssetToCategory,
} from "./roleAssetCategories";
import { RoleAssetCategorySection } from "./RoleAssetCategorySection";
import { roleFieldClass, rolePanelGhostButtonClass } from "./roleEditorStyles";

type RoleAssetCategoryGroupsProps = {
  /** Mount with `key={role.id}`: fold state and drafts belong to one role. */
  role: RoleRecord | null;
  bridgeReady: boolean;
  saving: boolean;
  /** The library image the preview pane shows. */
  focusedAssetPath: string;
  onPickAssets: (categoryId: string) => void;
  onFocusAsset: (path: string) => void;
  onUpdateOrganization: (
    categories: RoleAssetCategory[],
    bindings: Record<string, string>,
    removedIllustrations?: string[],
  ) => Promise<boolean>;
};

function newCategoryId(): string {
  const randomId = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID().replaceAll("-", "")
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `category-${randomId}`;
}

/** Renders the role's asset library by category, with category-local upload and drag-to-move. */
export function RoleAssetCategoryGroups({
  role,
  bridgeReady,
  saving,
  focusedAssetPath,
  onPickAssets,
  onFocusAsset,
  onUpdateOrganization,
}: RoleAssetCategoryGroupsProps) {
  const categories = getRoleAssetCategories(role);
  const [organizationDraft, setOrganizationDraft] = useState<{
    categories: RoleAssetCategory[];
    bindings: Record<string, string>;
  } | null>(null);
  // Initialized once per role (the parent keys this component by role id), so a manual fold survives saves.
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set(categories.map((category) => category.id)));
  const [creating, setCreating] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [draggedAssetPath, setDraggedAssetPath] = useState("");
  const [dropCategoryId, setDropCategoryId] = useState("");
  const [pendingDeleteCategory, setPendingDeleteCategory] = useState<RoleAssetCategory | null>(null);
  const visibleCategories = organizationDraft?.categories ?? categories;
  const visibleBindings = organizationDraft?.bindings ?? role?.asset_category_bindings ?? {};
  const groupedAssets = groupRoleAssetsByCategory(
    role ? { ...role, asset_categories: visibleCategories, asset_category_bindings: visibleBindings } : null,
  );
  const locked = !bridgeReady || saving;

  useEffect(() => {
    setOrganizationDraft(null);
  }, [role?.id, role?.updated_at]);

  async function persistOrganization(
    nextCategories: RoleAssetCategory[],
    nextBindings: Record<string, string>,
    removedIllustrations: string[] = [],
  ): Promise<boolean> {
    setOrganizationDraft({ categories: nextCategories, bindings: nextBindings });
    const persisted = await onUpdateOrganization(nextCategories, nextBindings, removedIllustrations);
    if (!persisted) setOrganizationDraft(null);
    return persisted;
  }

  function toggleCategory(categoryId: string): void {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  }

  function createCategory(): void {
    const name = newCategoryName.trim();
    if (!name || visibleCategories.some((category) => category.name.toLowerCase() === name.toLowerCase())) return;
    const id = newCategoryId();
    void persistOrganization([...visibleCategories, { id, name, allow_role_send: false }], visibleBindings);
    setExpandedIds((current) => new Set(current).add(id));
    setCreating(false);
    setNewCategoryName("");
  }

  function renameCategory(category: RoleAssetCategory, name: string): void {
    const normalized = name.trim();
    if (!normalized || normalized === category.name) return;
    if (visibleCategories.some((item) => item.id !== category.id && item.name.toLowerCase() === normalized.toLowerCase())) return;
    void persistOrganization(
      visibleCategories.map((item) => item.id === category.id ? { ...item, name: normalized } : item),
      visibleBindings,
    );
  }

  function toggleRoleSend(category: RoleAssetCategory): void {
    void persistOrganization(
      visibleCategories.map((item) => item.id === category.id ? { ...item, allow_role_send: !item.allow_role_send } : item),
      visibleBindings,
    );
  }

  async function confirmDeleteCategory(): Promise<void> {
    if (!pendingDeleteCategory) return;
    const categoryId = pendingDeleteCategory.id;
    const removedIllustrations = (groupedAssets.get(categoryId) ?? []).map((item) => item.relPath);
    const result = deleteRoleAssetCategory(visibleCategories, visibleBindings, categoryId);
    if (await persistOrganization(result.categories, result.bindings, removedIllustrations)) {
      setPendingDeleteCategory(null);
    }
  }

  function dropAsset(categoryId: string): void {
    if (draggedAssetPath) {
      const nextBindings = moveRoleAssetToCategory(visibleBindings, draggedAssetPath, categoryId);
      if (nextBindings !== visibleBindings) void persistOrganization(visibleCategories, nextBindings);
    }
    setDraggedAssetPath("");
    setDropCategoryId("");
  }

  return (
    <div className="grid content-start gap-2" data-testid="role-asset-library">
      <div className="flex min-h-9 items-center justify-between gap-3 px-2">
        <h2 className="m-0 text-title-sm text-ink">素材库</h2>
        <button className={rolePanelGhostButtonClass} type="button" disabled={locked} onClick={() => setCreating(true)}>
          <FolderSimplePlus className="h-4 w-4" aria-hidden="true" />
          新建分类
        </button>
      </div>
      {creating ? (
        <div className="px-2">
          <input
            autoFocus
            className={roleFieldClass}
            value={newCategoryName}
            placeholder="分类名称"
            aria-label="新分类名称"
            onChange={(event) => setNewCategoryName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") createCategory();
              if (event.key === "Escape") setCreating(false);
            }}
            onBlur={() => {
              if (newCategoryName.trim()) createCategory();
              else setCreating(false);
            }}
          />
        </div>
      ) : null}
      {visibleCategories.map((category) => (
        <RoleAssetCategorySection
          key={category.id}
          category={category}
          assets={groupedAssets.get(category.id) ?? []}
          expanded={expandedIds.has(category.id)}
          dropping={dropCategoryId === category.id}
          focusedAssetPath={focusedAssetPath}
          locked={locked}
          canDelete={visibleCategories.length > 1}
          onToggle={() => toggleCategory(category.id)}
          onRename={(name) => renameCategory(category, name)}
          onToggleRoleSend={() => toggleRoleSend(category)}
          onDelete={() => setPendingDeleteCategory(category)}
          onPickAssets={() => onPickAssets(category.id)}
          onFocusAsset={onFocusAsset}
          onDragAsset={(path) => {
            setDraggedAssetPath(path);
            if (!path) setDropCategoryId("");
          }}
          onDragOver={() => setDropCategoryId(category.id)}
          onDragLeave={() => setDropCategoryId((current) => current === category.id ? "" : current)}
          onDrop={() => dropAsset(category.id)}
        />
      ))}
      <ConfirmDialog
        open={Boolean(pendingDeleteCategory)}
        title="确认删除分类"
        description={pendingDeleteCategory
          ? `“${pendingDeleteCategory.name}” 删除后会同时移除其中 ${groupedAssets.get(pendingDeleteCategory.id)?.length ?? 0} 张素材。`
          : ""}
        confirmLabel="确认删除"
        busy={saving}
        onClose={() => setPendingDeleteCategory(null)}
        onConfirm={() => void confirmDeleteCategory()}
      />
    </div>
  );
}
