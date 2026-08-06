import { useEffect, useState } from "react";

import { useLatestRef } from "../shared/useLatestRef";
import type { RoleRecord } from "../shared/types";
import {
  applyRoleDifferenceProgress,
  createRoleDifferenceGenerationState,
  type RoleDifferenceGenerationState,
  type RoleDifferenceProgressPayload,
} from "./roleDifferenceGeneration";

type UseRoleDifferenceGenerationArgs = {
  roleId: string;
  onRoleUpdated: (role: RoleRecord) => void;
};

/** Coordinates one role-difference generation job and its bridge progress events. */
export function useRoleDifferenceGeneration({ roleId, onRoleUpdated }: UseRoleDifferenceGenerationArgs) {
  const [state, setState] = useState<RoleDifferenceGenerationState>(createRoleDifferenceGenerationState);
  const onRoleUpdatedRef = useLatestRef(onRoleUpdated);

  useEffect(() => {
    setState(createRoleDifferenceGenerationState());
  }, [roleId]);

  useEffect(() => {
    return window.miraDesktop.onEvent((event) => {
      if (event.method !== "roles.differences.progress") return;
      const payload = event.payload as RoleDifferenceProgressPayload;
      if (payload.role_id !== roleId) return;
      setState((current) => applyRoleDifferenceProgress(current, payload));
    });
  }, [roleId]);

  async function generate(baseAsset: string): Promise<void> {
    if (!roleId || !baseAsset || state.status === "running") return;
    setState((current) => ({
      ...createRoleDifferenceGenerationState(),
      status: "running",
    }));
    let response: Awaited<ReturnType<typeof window.miraDesktop.invoke>>;
    try {
      response = await window.miraDesktop.invoke({
        method: "roles.differences.generate",
        payload: {
          role_id: roleId,
          base_asset: baseAsset,
        },
      });
    } catch (reason) {
      setState((current) => ({
        ...current,
        status: "error",
        error: reason instanceof Error ? reason.message : String(reason),
      }));
      return;
    }
    if (response.error) {
      setState((current) => ({
        ...current,
        status: "error",
        error: response.error?.message ?? "差分生成失败",
      }));
      return;
    }
    const role = response.payload.role as RoleRecord | undefined;
    if (!role) {
      setState((current) => ({
        ...current,
        status: "error",
        error: "差分生成未返回角色素材",
      }));
      return;
    }
    setState((current) => ({
      ...current,
      status: "success",
      completed: current.stages.length,
      current: "",
      categoryName: typeof response.payload.category_name === "string"
        ? response.payload.category_name
        : current.categoryName,
      error: "",
      stages: current.stages.map((stage) => ({ ...stage, status: "completed", error: "" })),
    }));
    onRoleUpdatedRef.current(role);
  }

  return { state, generate };
}
