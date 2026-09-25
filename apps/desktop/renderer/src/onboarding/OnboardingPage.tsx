import { useState } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { TitleBar } from "../shell/TitleBar";
import { SettingsPage } from "../settings/SettingsPage";
import { useSettingsSubsectionMemory } from "../settings/useSettingsSubsectionMemory";
import { MascotOnStage } from "../shared/mascot/MascotOnStage";
import { SceneBackdrop } from "../shared/scene/SceneBackdrop";
import { scenePhaseAt } from "../shared/scene/timeOfDay";
import { onboardingSecondaryClass } from "./onboardingStyles";
import type { useOnboardingController } from "./useOnboardingController";
import { OnboardingStage } from "./OnboardingStage";

const noop = () => undefined;
const alwaysVisible = () => true;

/**
 * Standalone first-run screen; the workspace stays hidden until completion or
 * dismissal. Wiring only: the scene is `OnboardingStage`; the settings detour
 * reuses the real 设置 › 模型 page, laid over the paused scene.
 */
export function OnboardingPage({ controller, windowMaximized }: {
  controller: ReturnType<typeof useOnboardingController>;
  windowMaximized: boolean;
}) {
  // Read once: a guide that crosses a phase boundary keeps its scene.
  const [scenePhase] = useState(() => scenePhaseAt(new Date()));
  // Onboarding's settings visit is its own isolated mount — not nested under
  // the main app shell — so it owns its own subtab memory instead of
  // sharing main.tsx's instance.
  const settingsSubsectionMemory = useSettingsSubsectionMemory();
  // 吟风 stands in the scene and reacts in her dialogue, so the guide's own
  // error blocks (and the settings detour's) stay plain instead of adding her face again.
  return (
    <MascotOnStage>
      <div className="relative flex h-screen min-h-0 flex-col overflow-hidden text-ink" data-testid="onboarding-page">
        <SceneBackdrop phase={scenePhase} />
        <div className="relative z-[4] shrink-0">
          <TitleBar minimal sidebarCollapsed windowMaximized={windowMaximized} canGoBack={false} canGoForward={false} canRefreshSession={false}
            onToggleSidebar={noop} onGoBack={noop} onGoForward={noop} onRefreshSession={noop} />
        </div>
        <h1 className="sr-only">开始使用 Shiori</h1>
        {/* The scene stays mounted under the settings detour so 吟风 resumes at the same line. */}
        <OnboardingStage controller={controller} paused={controller.settingsOpen} />
        {controller.settingsOpen ? (
          <div className="absolute inset-x-0 bottom-0 top-[var(--titlebar-height)] z-[5] flex min-h-0 flex-col p-3 sm:p-5">
            <div className="surface-glass-strong motion-dialog-enter flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
              <div className="flex shrink-0 px-4 py-3">
                <button type="button" className={onboardingSecondaryClass} onClick={() => { controller.setSettingsOpen(false); void controller.refresh(); }}>
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />返回引导
                </button>
              </div>
              <div className="min-h-0 flex-1">
                <SettingsPage
                  bridgeReady={Boolean(controller.data)}
                  section="models"
                  isSectionVisible={alwaysVisible}
                  isPluginEnabled={alwaysVisible}
                  activeSubsections={settingsSubsectionMemory.activeSubsections}
                  onChangeSubsection={settingsSubsectionMemory.remember}
                />
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </MascotOnStage>
  );
}
