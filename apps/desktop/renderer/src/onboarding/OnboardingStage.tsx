import { useState } from "react";
import { useBridgeOfflineFeedbackFilter } from "../app/bridgeOfflineFeedback";
import { AdvDialogueBox } from "../shared/adv/AdvDialogueBox";
import { useAdvKeyboard } from "../shared/adv/useAdvKeyboard";
import { mascotName } from "../shared/mascot/mascotExpressions";
import { mascotSprites } from "../shared/mascot/mascotSprites";
import { cx } from "../shared/styles";
import { OnboardingMascot } from "./OnboardingMascot";
import { OnboardingProgress } from "./OnboardingProgress";
import { OnboardingStepCard } from "./OnboardingStepCard";
import { canSkipOnboardingStep, selectOnboardingScene } from "./onboardingSteps";
import { onboardingSecondaryClass } from "./onboardingStyles";
import type { useOnboardingController } from "./useOnboardingController";
import { useOnboardingScene } from "./useOnboardingScene";

/**
 * The guide as a galgame scene: 吟风 on the right, the step indicator and
 * 「跳过」 on top, the step's form card floating on the left once her lines
 * reach it, and her dialogue box along the bottom. Clicking the scene, Enter
 * or Space advances her lines; the card itself never advances them.
 */
export function OnboardingStage({ controller, paused }: {
  controller: ReturnType<typeof useOnboardingController>;
  /** Covered by the settings detour: typing and keys stop, state is kept. */
  paused: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const { progress, data, error } = controller;
  const step = progress?.step;
  const scene = selectOnboardingScene({ error, hasData: Boolean(data), step });
  const roles = data?.roles ?? [];
  const [selectedRoleId, setSelectedRoleId] = useState(() => window.localStorage.getItem("miraDesktop.activeRoleId") ?? "");
  const role = roles.find((item) => item.id === selectedRoleId) ?? roles[0];
  const director = useOnboardingScene({ scene, roleName: role?.name ?? "", paused, onSkip: controller.skip });
  const { dialogue } = director;
  const line = dialogue.line;
  const expression = line?.expression ?? "neutral";
  useAdvKeyboard(!paused && line !== null, director.advance);
  // The error card is the guide's offline banner: toasts that only restate it are dropped.
  useBridgeOfflineFeedbackFilter(scene === "offline", error);
  const locked = busy || controller.entering || director.leaving;
  return (
    <main className="onboarding-stage relative min-h-0 flex-1" inert={paused} aria-hidden={paused || undefined}>
      <OnboardingMascot expression={expression} cue={dialogue.serial} />
      <button type="button" aria-label="继续对话" tabIndex={-1} onClick={director.advance}
        className="absolute inset-0 z-[2] h-full w-full cursor-default bg-transparent" />
      <div className="onboarding-layout pointer-events-none relative z-[3] grid h-full min-h-0">
        <div className="flex items-center justify-between gap-3">
          <OnboardingProgress step={step} />
          {canSkipOnboardingStep(step) && !director.leaving ? (
            <button type="button" className={cx(onboardingSecondaryClass, "pointer-events-auto")} onClick={director.skip}
              disabled={!controller.canSkip || locked}>跳过</button>
          ) : null}
        </div>
        <div className="onboarding-card-slot flex min-h-0 items-center">
          {director.formVisible ? (
            <OnboardingStepCard scene={scene} controller={controller} role={role} roles={roles} locked={locked}
              onSelectRole={setSelectedRoleId} onBusyChange={setBusy} onReact={director.react} />
          ) : null}
        </div>
        {line ? (
          <AdvDialogueBox className="onboarding-adv" speaker={mascotName} avatarSrc={mascotSprites[expression]}
            text={line.text} shownChars={dialogue.shownChars} waiting={dialogue.complete && (!dialogue.lastLine || director.leaving)} />
        ) : <p role="status" className="sr-only">正在连接</p>}
      </div>
    </main>
  );
}
