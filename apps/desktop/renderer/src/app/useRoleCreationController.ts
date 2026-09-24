import { useState } from "react";
import { createEmptyNewRoleForm } from "./appState";
import { useLatestRef } from "../shared/useLatestRef";
import { cancelRoleCreation, resetRoleCreationForm, runRoleCreation } from "./roleCreationWorkflow";
import type { RoleCreationControllerArgs } from "./roleCreationWorkflow";
import { useRoleCreationDraft } from "../roles/useRoleCreationDraft";

/** Assembles the new-role draft, import lifecycle, and creation workflow. */
export function useRoleCreationController(args: RoleCreationControllerArgs) {
  const [creating, setCreating] = useState(false);
  const creatingRef = useLatestRef(creating);
  const imports = useRoleCreationDraft(args.feedback.error);
  const { newRoleForm, newRoleFormRef, updateNewRoleForm } = imports;
  const formActions = { ...args, updateNewRoleForm };

  function resetNewRoleForm() {
    if (creatingRef.current) return;
    void imports.cancelRoleCardImport();
    resetRoleCreationForm(formActions);
  }

  function cancelCreateRole() {
    if (creatingRef.current) return;
    void imports.cancelRoleCardImport();
    cancelRoleCreation({ ...formActions, creating: false });
  }

  async function createRole() {
    if (creatingRef.current || imports.roleCardImport.status === "previewing") return;
    creatingRef.current = true;
    try {
      const created = await runRoleCreation(newRoleFormRef.current, {
        ...args, setCreating, invoke: window.miraDesktop.invoke,
      });
      if (created) {
        imports.clearRoleCardImport();
        updateNewRoleForm(createEmptyNewRoleForm());
      }
    } finally {
      creatingRef.current = false;
    }
  }

  return {
    creating, newRoleForm, updateNewRoleForm, resetNewRoleForm, cancelCreateRole, createRole,
    roleCardImport: imports.roleCardImport,
    previewRoleCard: imports.previewRoleCard,
    cancelRoleCardImport: () => { if (!creatingRef.current) return imports.cancelRoleCardImport(); },
  };
}
