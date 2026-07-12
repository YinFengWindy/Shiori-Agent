import { useEffect, useState } from "react";

import { BackIcon, DeleteIcon, PlusIcon, SendIcon, UploadIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import type { RoleAssetCategory, RoleRecord } from "../shared/types";
import { toFileUrl } from "../shared/format";
import {
  getRoleAssetCategories,
  groupRoleAssetsByCategory,
  moveRoleAssetToCategory,
  removeRoleAssetCategory,
} from "./roleAssetCategories";

type RoleAssetCategoryGroupsProps = {
  role: RoleRecord | null;
  bridgeReady: boolean;
  saving: boolean;
  selectedAssetPath: string;
  onBackToDetail: () => void;
  onPickAssets: (categoryId: string) => void;
  onRemoveAsset: (path: string) => void;
  onSelectAsset: (path: string) => void;
  onUpdateOrganization: (
    categories: RoleAssetCategory[],
    bindings: Record<string, string>,
  ) => Promise<boolean>;
};

/** Renders grouped role assets with category-local upload and drag-to-move controls. */
export function RoleAssetCategoryGroups({
  role,
  bridgeReady,
  saving,
  selectedAssetPath,
  onBackToDetail,
  onPickAssets,
  onRemoveAsset,
  onSelectAsset,
  onUpdateOrganization,
}: RoleAssetCategoryGroupsProps) {
  const categories = getRoleAssetCategories(role);
  const [organizationDraft, setOrganizationDraft] = useState<{
    categories: RoleAssetCategory[];
    bindings: Record<string, string>;
  } | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [draggedAssetPath, setDraggedAssetPath] = useState("");
  const [dropCategoryId, setDropCategoryId] = useState("");
  const visibleCategories = organizationDraft?.categories ?? categories;
  const visibleBindings = organizationDraft?.bindings ?? role?.asset_category_bindings ?? {};
  const groupedAssets = groupRoleAssetsByCategory(
    role ? {
      ...role,
      asset_categories: visibleCategories,
      asset_category_bindings: visibleBindings,
    } : null,
  );

  useEffect(() => {
    setOrganizationDraft(null);
  }, [role?.id, role?.updated_at]);

  async function persistOrganization(
    nextCategories: RoleAssetCategory[],
    nextBindings: Record<string, string>,
  ): Promise<void> {
    setOrganizationDraft({ categories: nextCategories, bindings: nextBindings });
    const persisted = await onUpdateOrganization(nextCategories, nextBindings);
    if (!persisted) {
      setOrganizationDraft(null);
    }
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
    if (!name || visibleCategories.some((category) => category.name.toLowerCase() === name.toLowerCase())) {
      return;
    }
    const randomId = typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID().replaceAll("-", "")
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const id = `category-${randomId}`;
    void persistOrganization(
      [...visibleCategories, { id, name, allow_role_send: false }],
      visibleBindings,
    );
    setExpandedIds((current) => new Set(current).add(id));
    setCreating(false);
    setNewCategoryName("");
  }

  function renameCategory(category: RoleAssetCategory, name: string): void {
    const normalized = name.trim();
    if (!normalized || normalized === category.name) return;
    if (visibleCategories.some((item) => item.id !== category.id && item.name.toLowerCase() === normalized.toLowerCase())) {
      return;
    }
    void persistOrganization(
      visibleCategories.map((item) => item.id === category.id ? { ...item, name: normalized } : item),
      visibleBindings,
    );
  }

  function toggleRoleSend(category: RoleAssetCategory): void {
    void persistOrganization(
      visibleCategories.map((item) => item.id === category.id
        ? { ...item, allow_role_send: !item.allow_role_send }
        : item),
      visibleBindings,
    );
  }

  function deleteCategory(category: RoleAssetCategory): void {
    const destination = visibleCategories.find((item) => item.id !== category.id);
    if (!destination) return;
    const assetCount = groupedAssets.get(category.id)?.length ?? 0;
    const confirmed = window.confirm(
      assetCount
        ? `删除“${category.name}”并将其中 ${assetCount} 张素材移动到“${destination.name}”？`
        : `删除“${category.name}”？`,
    );
    if (!confirmed) return;
    const result = removeRoleAssetCategory(
      visibleCategories,
      visibleBindings,
      category.id,
      destination.id,
    );
    void persistOrganization(result.categories, result.bindings);
  }

  function dropAsset(categoryId: string): void {
    if (!draggedAssetPath) return;
    const currentBindings = visibleBindings;
    const nextBindings = moveRoleAssetToCategory(
      currentBindings,
      draggedAssetPath,
      categoryId,
    );
    if (nextBindings !== currentBindings) {
      void persistOrganization(visibleCategories, nextBindings);
    }
    setDraggedAssetPath("");
    setDropCategoryId("");
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between px-2 pb-3">
        <button
          className="grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white text-[#111111] shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] hover:shadow-[0_14px_28px_rgba(15,23,42,0.14)] focus:outline-none"
          type="button"
          aria-label="返回角色详情"
          title="返回角色详情"
          onClick={onBackToDetail}
        >
          <BackIcon className="h-5 w-5 fill-current" />
        </button>
        <button
          className="grid h-10 w-10 place-items-center rounded-md border border-black/8 bg-white text-[#272536] transition hover:bg-[#F5F7FA] focus:outline-none"
          type="button"
          aria-label="新建分类"
          title="新建分类"
          disabled={!bridgeReady || saving}
          onClick={() => setCreating(true)}
        >
          <PlusIcon className="h-4 w-4 fill-current" />
        </button>
      </div>
      {creating ? (
        <div className="mb-2 flex items-center gap-2 px-2">
          <input
            autoFocus
            className="h-10 min-w-0 flex-1 rounded-md border border-[#D8DFE7] bg-white px-3 text-sm transition focus:border-[#B8BEC7] focus:outline-none focus:ring-2 focus:ring-gray-300/70"
            value={newCategoryName}
            placeholder="分类名称"
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
      <div className="scrollbar-soft min-h-0 flex-1 overflow-y-auto px-2">
        {visibleCategories.map((category) => {
          const assets = groupedAssets.get(category.id) ?? [];
          const expanded = expandedIds.has(category.id);
          const dropping = dropCategoryId === category.id;
          return (
            <section
              className={cx(
                "mb-2 rounded-md border transition",
                dropping ? "border-[#7C6EE6] bg-[#F6F4FF]" : "border-[#E2E6EB] bg-white",
              )}
              key={category.id}
              onDragOver={(event) => {
                event.preventDefault();
                setDropCategoryId(category.id);
              }}
              onDragLeave={() => setDropCategoryId((current) => current === category.id ? "" : current)}
              onDrop={(event) => {
                event.preventDefault();
                dropAsset(category.id);
              }}
            >
              <div className="flex min-h-12 items-center gap-2 px-2.5">
                <button
                  className="grid h-8 w-8 place-items-center rounded-md text-[#626B77] transition hover:bg-[#F2F4F7] focus:outline-none"
                  type="button"
                  aria-label={expanded ? `收起${category.name}` : `展开${category.name}`}
                  onClick={() => toggleCategory(category.id)}
                >
                  <span className={cx("text-lg transition-transform", expanded && "rotate-90")}>›</span>
                </button>
                <input
            className="h-8 min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1 text-sm font-medium transition focus:border-[#B8BEC7] focus:bg-white focus:outline-none focus:ring-2 focus:ring-gray-300/70"
                  defaultValue={category.name}
                  aria-label={`${category.name}分类名称`}
                  onBlur={(event) => renameCategory(category, event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.currentTarget.blur();
                  }}
                />
                <span className="min-w-6 text-center text-xs text-[#7A8593]">{assets.length}</span>
                <button
                  className={cx(
                    "grid h-8 w-8 place-items-center rounded-md transition focus:outline-none",
                    category.allow_role_send
                      ? "bg-[#272536] text-white"
                      : "text-[#8A94A2] hover:bg-[#F2F4F7] hover:text-[#272536]",
                  )}
                  type="button"
                  aria-label={category.allow_role_send ? "禁止角色发送此分类" : "允许角色发送此分类"}
                  title={category.allow_role_send ? "角色可发送" : "角色不可发送"}
                  disabled={!bridgeReady || saving}
                  onClick={() => toggleRoleSend(category)}
                >
                  <SendIcon className="h-4 w-4 fill-current" />
                </button>
                <button
                  className="grid h-8 w-8 place-items-center rounded-md text-[#8A94A2] transition hover:bg-[#F2F4F7] hover:text-[#C16E4E] focus:outline-none"
                  type="button"
                  aria-label={`删除分类${category.name}`}
                  disabled={!bridgeReady || saving || visibleCategories.length === 1}
                  onClick={() => deleteCategory(category)}
                >
                  <DeleteIcon className="h-3.5 w-3.5 fill-current" />
                </button>
              </div>
              {expanded ? (
                <div className="grid grid-cols-4 gap-2.5 border-t border-[#ECEFF3] p-3">
                  {assets.map(({ relPath, absPath }) => (
                    <div className="group relative h-[82px] w-[82px]" key={relPath}>
                      <button
                        className={cx(
                          "h-[82px] w-[82px] overflow-hidden rounded-md border p-0 transition",
                          selectedAssetPath === relPath
                            ? "border-[#272536] shadow-[0_8px_18px_rgba(39,37,54,0.14)]"
                            : "border-[#D8DFE7] hover:border-[#9AA3B2]",
                        )}
                        type="button"
                        draggable
                        onDragStart={() => setDraggedAssetPath(relPath)}
                        onDragEnd={() => {
                          setDraggedAssetPath("");
                          setDropCategoryId("");
                        }}
                        onClick={() => onSelectAsset(relPath)}
                      >
                        <img className="h-full w-full object-cover" src={toFileUrl(absPath)} alt="role asset" />
                      </button>
                      <button
                        className="absolute right-1 top-1 grid h-6 w-6 place-items-center rounded-md bg-white/92 text-[#5B6472] opacity-0 shadow transition group-hover:opacity-100 focus:opacity-100"
                        type="button"
                        aria-label="删除素材"
                        disabled={!bridgeReady || saving}
                        onClick={() => onRemoveAsset(relPath)}
                      >
                        <DeleteIcon className="h-3 w-3 fill-current" />
                      </button>
                    </div>
                  ))}
                  <button
                    className="grid h-[82px] w-[82px] place-items-center rounded-md border border-dashed border-[#C9D0D9] bg-[#FAFBFC] text-[#67717E] transition hover:border-[#9AA3B2] hover:bg-[#F4F6F8] focus:outline-none"
                    type="button"
                    aria-label={`上传到${category.name}`}
                    title={`上传到${category.name}`}
                    disabled={!bridgeReady || saving}
                    onClick={() => onPickAssets(category.id)}
                  >
                    <UploadIcon className="h-6 w-6 fill-current" />
                  </button>
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    </div>
  );
}
