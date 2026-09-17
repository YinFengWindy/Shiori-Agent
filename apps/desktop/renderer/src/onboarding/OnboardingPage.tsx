import { useState } from "react";
import { ArrowLeft, ArrowsClockwise, GearSix } from "@phosphor-icons/react";
import { TitleBar } from "../shell/TitleBar";
import { SettingsPage } from "../settings/SettingsPage";
import { useSettingsSubsectionMemory } from "../settings/useSettingsSubsectionMemory";
import type { useOnboardingController } from "./useOnboardingController";
import { OnboardingModelStep } from "./OnboardingModelStep";
import { OnboardingRoleStep } from "./OnboardingRoleStep";
import { OnboardingWorkspaceStep } from "./OnboardingWorkspaceStep";
import { cx } from "../shared/styles";

const steps = [{ id: "model", label: "注册模型" }, { id: "role", label: "创建角色" }, { id: "workspace", label: "进入工作区" }] as const;
const noop = () => undefined;
const alwaysVisible = () => true;

/** Standalone first-run screen; the workspace stays hidden until completion or dismissal. */
export function OnboardingPage({ controller, windowMaximized }: {
  controller: ReturnType<typeof useOnboardingController>;
  windowMaximized: boolean;
}) {
  const [busy, setBusy] = useState(false);
  // Onboarding's settings visit is its own isolated mount — not nested under
  // the main app shell — so it owns its own subtab memory instead of
  // sharing main.tsx's instance.
  const settingsSubsectionMemory = useSettingsSubsectionMemory();
  const { progress, data, error, loading, settingsOpen } = controller;
  const step = progress?.step;
  const index = steps.findIndex((item) => item.id === step);
  const locked = busy || controller.entering;
  return (
    <div className="flex h-screen min-h-0 flex-col bg-gradient-app bg-fixed text-ink" data-testid="onboarding-page">
      <TitleBar minimal sidebarCollapsed windowMaximized={windowMaximized} canGoBack={false} canGoForward={false} canRefreshSession={false}
        onToggleSidebar={noop} onGoBack={noop} onGoForward={noop} onRefreshSession={noop} />
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-line-soft px-6 py-4 sm:px-10">
        <span className="text-xl font-medium">Shiori</span>
        <button type="button" className="rounded-md px-3 py-2 text-sm text-ink-muted hover:bg-black/5 disabled:opacity-40"
          onClick={controller.skip} disabled={!controller.canSkip || locked}>暂时跳过</button>
      </header>
      {settingsOpen ? <>
        <div className="flex shrink-0 px-6 py-3"><button type="button" onClick={() => { controller.setSettingsOpen(false); void controller.refresh(); }}
          className="inline-flex items-center gap-2 rounded-md p-2 text-sm"><ArrowLeft size={18} />返回引导</button></div>
        <div className="min-h-0 flex-1">
          <SettingsPage
            bridgeReady={Boolean(data)}
            section="models"
            isSectionVisible={alwaysVisible}
            isPluginEnabled={alwaysVisible}
            activeSubsections={settingsSubsectionMemory.activeSubsections}
            onChangeSubsection={settingsSubsectionMemory.remember}
          />
        </div>
      </> : <main className="scrollbar-soft min-h-0 flex-1 overflow-y-auto px-6 pb-10 pt-8 sm:px-10">
        <div className="mx-auto w-full max-w-[680px]">
          <nav aria-label="首次设置进度" className="mb-9 flex flex-wrap gap-x-6 gap-y-3 text-xs text-ink-faint">
            {steps.filter((_, position) => index < 0 || position >= index).map((item) => (
              <span key={item.id} aria-current={item.id === step ? "step" : undefined}
                className={cx("flex items-center gap-2", item.id === step && "font-medium text-accent-text")}>
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-current">{steps.indexOf(item) + 1}</span>{item.label}
              </span>
            ))}
          </nav>
          <h1 className="mb-6 text-2xl font-medium">{steps.find((item) => item.id === step)?.label ?? "开始使用 Shiori"}</h1>
          {error ? <div className="mb-6 border-l-2 border-[var(--danger-300)] bg-danger-soft px-4 py-3">
            <p role="alert" className="break-words text-sm leading-6 text-danger-text">{error}</p>
            <div className="mt-3 flex flex-wrap gap-4 text-sm">
              <button type="button" disabled={loading || locked} onClick={() => void controller.retry()} className="inline-flex items-center gap-2 disabled:opacity-40"><ArrowsClockwise size={18} />重试连接</button>
              <button type="button" disabled={locked} onClick={() => controller.setSettingsOpen(true)} className="inline-flex items-center gap-2"><GearSix size={18} />模型注册设置</button>
            </div>
          </div> : null}
          {!step && !error ? <p role="status" className="py-12 text-sm text-ink-muted">正在连接...</p> : null}
          <fieldset disabled={!data || loading || controller.entering} className="min-w-0">
            {step === "model" ? <OnboardingModelStep onSaved={controller.refresh} onBusyChange={setBusy} /> : null}
            {step === "role" ? <OnboardingRoleStep onSaved={controller.refresh} onBusyChange={setBusy} /> : null}
            {step === "workspace" ? <OnboardingWorkspaceStep roles={data?.roles ?? []} entering={controller.entering} onEnter={controller.enterWorkspace} /> : null}
          </fieldset>
        </div>
      </main>}
    </div>
  );
}
