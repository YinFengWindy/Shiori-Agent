import { createContext, useContext, type ReactNode } from "react";
import { useMascotEnabled } from "./useMascotEnabled";

const OnStageContext = createContext(false);

/**
 * Marks a subtree where 吟风 is already standing in person (the first-run
 * guide, 设置 › 关于, a confirmation she fronts). Inline errors inside it
 * drop her face and line and keep only the plain message, so she never
 * appears twice on one screen.
 */
export function MascotOnStage({ active = true, children }: { active?: boolean; children: ReactNode }) {
  const outer = useContext(OnStageContext);
  return <OnStageContext.Provider value={outer || active}>{children}</OnStageContext.Provider>;
}

/**
 * Whether a small 吟风 (face + line) may front something here: the 看板娘
 * is on (设置 › 外观) and she is not already on stage in this subtree.
 */
export function useMascotCameoAllowed() {
  const enabled = useMascotEnabled();
  const onStage = useContext(OnStageContext);
  return enabled && !onStage;
}
