import type { RoleAssetCategory, RoleRecord } from "../shared/types";

export type RoleAssetPair = {
  relPath: string;
  absPath: string;
};

/** Returns normalized categories and preserves a default group for legacy role payloads. */
export function getRoleAssetCategories(role: RoleRecord | null): RoleAssetCategory[] {
  if (role?.asset_categories?.length) {
    return role.asset_categories;
  }
  return [{ id: "default", name: "默认", allow_role_send: false }];
}

/** Groups role assets by their single category while keeping bridge path order. */
export function groupRoleAssetsByCategory(
  role: RoleRecord | null,
): Map<string, RoleAssetPair[]> {
  const categories = getRoleAssetCategories(role);
  const fallbackCategoryId = categories[0]!.id;
  const groups = new Map(categories.map((category) => [category.id, [] as RoleAssetPair[]]));
  (role?.illustrations ?? []).forEach((relPath, index) => {
    const requestedCategoryId = role?.asset_category_bindings?.[relPath] ?? fallbackCategoryId;
    const categoryId = groups.has(requestedCategoryId) ? requestedCategoryId : fallbackCategoryId;
    groups.get(categoryId)!.push({
      relPath,
      absPath: role?.illustrations_abs[index] ?? "",
    });
  });
  return groups;
}

/** Moves one role asset to a category without mutating the current bindings. */
export function moveRoleAssetToCategory(
  bindings: Record<string, string>,
  relPath: string,
  categoryId: string,
): Record<string, string> {
  if (bindings[relPath] === categoryId) {
    return bindings;
  }
  return { ...bindings, [relPath]: categoryId };
}

/** Removes a category after reassigning all of its assets to another category. */
export function removeRoleAssetCategory(
  categories: RoleAssetCategory[],
  bindings: Record<string, string>,
  categoryId: string,
  destinationCategoryId: string,
) {
  return {
    categories: categories.filter((category) => category.id !== categoryId),
    bindings: Object.fromEntries(
      Object.entries(bindings).map(([path, currentCategoryId]) => [
        path,
        currentCategoryId === categoryId ? destinationCategoryId : currentCategoryId,
      ]),
    ),
  };
}
