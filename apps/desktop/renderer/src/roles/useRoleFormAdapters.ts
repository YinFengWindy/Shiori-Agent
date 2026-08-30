import type React from "react";
import type { RoleFormState } from "../shared/types";

type MutableValue<T> = { current: T };

type UseRoleFormAdaptersArgs = {
  roleFormRef: MutableValue<RoleFormState>;
  setRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
};

/** Adapts role form state setters while keeping async consumers' latest-value refs synchronized. */
export function useRoleFormAdapters({
  roleFormRef,
  setRoleForm,
}: UseRoleFormAdaptersArgs) {
  function updateRoleForm(next: React.SetStateAction<RoleFormState>): void {
    const resolved = typeof next === "function" ? next(roleFormRef.current) : next;
    roleFormRef.current = resolved;
    setRoleForm(resolved);
  }

  return { updateRoleForm };
}
