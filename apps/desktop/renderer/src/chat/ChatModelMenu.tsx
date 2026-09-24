import { CaretRight, Check } from "@phosphor-icons/react";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import type { RoleRecord } from "../shared/types";
import {
  runtimeConfigForSelection,
  selectionFromRole,
  type ModelEffort,
  type RoleModelSelection,
} from "./chatModelSelection";
import { getChatModelMenuPosition } from "./chatModelMenuLayout";
import { MenuItem, MenuPanel, menuLabelClass } from "../shared/ui/Menu";
import { errorMessage, feedback } from "../shared/feedback/feedbackStore";
import { subscribeChatModelMenuRequests } from "./chatModelMenuRequests";

type ChatModelMenuProps = {
  activeRoleId: string;
  bridgeReady: boolean;
};

/** Owns the compact role-level model and dialogue effort selectors. */
export function ChatModelMenu({ activeRoleId, bridgeReady }: ChatModelMenuProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [submenu, setSubmenu] = useState<"dialogue" | "visual" | null>(null);
  const [hoveredModelId, setHoveredModelId] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ left: number; bottom: number } | null>(null);
  const [registrations, setRegistrations] = useState<ModelRegistrationFormData[]>([]);
  const [selection, setSelection] = useState<RoleModelSelection | null>(null);

  const loadSelection = useEffectEvent(async () => {
    if (!activeRoleId || !bridgeReady) return;
    try {
      const [settings, rolesResponse] = await Promise.all([
        window.miraDesktop.readSettings(),
        window.miraDesktop.invoke({ method: "roles.list", payload: {} }),
      ]);
      if (rolesResponse.error) throw new Error(rolesResponse.error.message);
      const roles = Array.isArray(rolesResponse.payload.roles)
        ? rolesResponse.payload.roles as RoleRecord[]
        : [];
      const role = roles.find((item) => item.id === activeRoleId);
      if (!role) throw new Error("当前角色不存在");
      setRegistrations(settings.formData.models.registrations);
      setSelection(selectionFromRole(role, settings.formData.models.registrations));
    } catch (error) {
      feedback.error(`模型选项加载失败：${errorMessage(error)}`);
    }
  });

  useEffect(() => {
    setOpen(false);
    setSubmenu(null);
    setHoveredModelId(null);
    setMenuPosition(null);
    setSelection(null);
    void loadSelection();
  }, [activeRoleId, bridgeReady]);

  // Opened on request (e.g. the "选择模型" action of a send that failed for
  // lack of a model), straight onto the dialogue-model list. The selection is
  // re-read first: the failure means the cached one may already be stale.
  useEffect(() => subscribeChatModelMenuRequests(() => {
    void loadSelection();
    setOpen(true);
    setSubmenu("dialogue");
    setHoveredModelId(null);
  }), []);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: PointerEvent) => {
      if (containerRef.current?.contains(event.target as Node) || menuRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [open]);

  useEffect(() => {
    if (!open || !containerRef.current) return undefined;
    const updatePosition = () => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      setMenuPosition(getChatModelMenuPosition(rect, window.innerHeight));
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  async function updateSelection(kind: "dialogue" | "visual" | "dialogueEffort" | "visualEffort", value: string): Promise<void> {
    if (!selection || !activeRoleId) return;
    const runtimeConfig = runtimeConfigForSelection(selection, kind, value);
    try {
      const response = await window.miraDesktop.invoke({
        method: "roles.update",
        payload: { role_id: activeRoleId, runtime_config: runtimeConfig },
      });
      if (response.error) throw new Error(response.error.message);
      const role = response.payload.role as RoleRecord | undefined;
      setSelection(role ? selectionFromRole(role, registrations) : {
        dialogueId: String(runtimeConfig.dialogue_model_registration_id),
        visualId: String(runtimeConfig.visual_model_registration_id),
        dialogueEffort: String(runtimeConfig.dialogue_model_effort) as ModelEffort,
        visualEffort: String(runtimeConfig.visual_model_effort) as ModelEffort,
        runtimeConfig,
      });
    } catch (error) {
      feedback.error(`模型切换失败：${errorMessage(error)}`);
    }
  }

  const chatModel = registrations.find((item) => item.id === selection?.dialogueId);
  if (!activeRoleId) return null;

  return (
    <div className="relative" ref={containerRef}>
      <button
        className="inline-flex h-[30px] max-w-[190px] items-center rounded-md px-2 text-xs text-ink-secondary transition hover:bg-surface-soft hover:text-ink focus:outline-none disabled:opacity-40"
        type="button"
        aria-label="选择聊天模型"
        aria-expanded={open}
        disabled={!bridgeReady || !selection}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="truncate">{chatModel?.model ?? "选择聊天模型"}</span>
      </button>
      {open && selection && menuPosition ? createPortal(
        <div ref={menuRef} className="fixed z-50 flex items-end gap-1.5" style={menuPosition}>
          <MenuPanel className="grid w-[112px] content-start gap-1">
            {(["dialogue", "visual"] as const).map((kind) => (
              <MenuItem key={kind} className="h-9 justify-between" selected={submenu === kind} onMouseEnter={() => { setSubmenu(kind); setHoveredModelId(null); }} onClick={() => { setSubmenu(kind); setHoveredModelId(null); }}>
                <span>{kind === "dialogue" ? "聊天模型" : "识图模型"}</span><CaretRight className="h-3 w-3" weight="bold" aria-hidden="true" />
              </MenuItem>
            ))}
          </MenuPanel>
          {submenu ? (
            <MenuPanel className="relative min-w-[132px]">
              <div className="grid gap-1">
                {(submenu === "visual" ? [{ id: "", model: "沿用对话模型" }, ...registrations] : registrations).map((registration) => (
                  <MenuItem key={registration.id || "dialogue-fallback"} className="h-9 justify-between" selected={(submenu === "dialogue" ? selection.dialogueId : selection.visualId) === registration.id} onMouseEnter={() => setHoveredModelId(registration.id)} onClick={() => void updateSelection(submenu, registration.id)}>
                    <span className="max-w-[150px] truncate">{registration.model}</span><span className="flex items-center gap-1" aria-hidden="true">{(submenu === "dialogue" ? selection.dialogueId : selection.visualId) === registration.id ? <Check className="h-3 w-3" weight="bold" /> : null}<CaretRight className="h-3 w-3" weight="bold" /></span>
                  </MenuItem>
                ))}
              </div>
              {hoveredModelId !== null ? (
                <MenuPanel className="absolute left-full top-0 ml-1 grid min-w-[150px] gap-1">
                  <span className={menuLabelClass}>思考强度</span>
                  {(["none", "low", "high", "max"] as const).map((effort) => {
                    const selected = (submenu === "dialogue" ? selection.dialogueEffort : selection.visualEffort) === effort;
                    return <MenuItem key={effort} className="justify-between" selected={selected} onClick={() => void updateSelection(submenu === "dialogue" ? "dialogueEffort" : "visualEffort", effort)}><span>{effort === "none" ? "关闭" : effort === "low" ? "低" : effort === "high" ? "高" : "最大"}</span>{selected ? <Check className="h-3 w-3" weight="bold" aria-hidden="true" /> : null}</MenuItem>;
                  })}
                </MenuPanel>
              ) : null}
            </MenuPanel>
          ) : null}
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
