import type { RoleRecord } from "../shared/types";
import { OnboardingErrorCard } from "./OnboardingErrorCard";
import { OnboardingModelStep } from "./OnboardingModelStep";
import { OnboardingRoleStep } from "./OnboardingRoleStep";
import { OnboardingWorkspaceStep } from "./OnboardingWorkspaceStep";
import type { OnboardingReaction, OnboardingScene } from "./onboardingScript";
import type { useOnboardingController } from "./useOnboardingController";

/** Picks the floating card for the current scene: a step's form, or the error area. */
export function OnboardingStepCard({ scene, controller, role, roles, locked, onSelectRole, onBusyChange, onReact }: {
  scene: OnboardingScene;
  controller: ReturnType<typeof useOnboardingController>;
  role: RoleRecord | undefined;
  roles: RoleRecord[];
  locked: boolean;
  onSelectRole: (roleId: string) => void;
  onBusyChange: (busy: boolean) => void;
  onReact: (reaction: OnboardingReaction) => void;
}) {
  if (scene === "offline" || scene === "failed") {
    return (
      <OnboardingErrorCard title={scene === "offline" ? "连接桥" : "进入 Shiori"} error={controller.error}
        retrying={controller.loading} disabled={locked}
        onRetry={() => void controller.retry()} onOpenSettings={() => controller.setSettingsOpen(true)} />
    );
  }
  // Reads in flight or a workspace entry freeze the form without hiding it.
  const frozen = !controller.data || controller.loading || controller.entering;
  return (
    <fieldset disabled={frozen} className="contents">
      {scene === "model" ? <OnboardingModelStep onSaved={controller.refresh} onBusyChange={onBusyChange} onReact={onReact} /> : null}
      {scene === "role" ? <OnboardingRoleStep onSaved={controller.refresh} onBusyChange={onBusyChange} onReact={onReact} /> : null}
      {scene === "workspace" && role ? (
        <OnboardingWorkspaceStep roles={roles} role={role} entering={controller.entering} onSelect={onSelectRole} onEnter={controller.enterWorkspace} />
      ) : null}
    </fieldset>
  );
}
