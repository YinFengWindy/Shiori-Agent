import type React from "react";
import type { NewRoleFormState, RoleFormState } from "../shared/types";

type MutableValue<T> = { current: T };

type UseRoleFormAdaptersArgs = {
  roleFormRef: MutableValue<RoleFormState>;
  newRoleFormRef: MutableValue<NewRoleFormState>;
  setRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  setNewRoleForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
};

/** Adapts role form state setters while keeping async consumers' latest-value refs synchronized. */
export function useRoleFormAdapters({
  roleFormRef,
  newRoleFormRef,
  setRoleForm,
  setNewRoleForm,
}: UseRoleFormAdaptersArgs) {
  function updateRoleForm(next: React.SetStateAction<RoleFormState>): void {
    const resolved = typeof next === "function" ? next(roleFormRef.current) : next;
    roleFormRef.current = resolved;
    setRoleForm(resolved);
  }

  function updateNewRoleForm(next: React.SetStateAction<NewRoleFormState>): void {
    const resolved = typeof next === "function" ? next(newRoleFormRef.current) : next;
    newRoleFormRef.current = resolved;
    setNewRoleForm(resolved);
  }

  return { updateRoleForm, updateNewRoleForm };
}
