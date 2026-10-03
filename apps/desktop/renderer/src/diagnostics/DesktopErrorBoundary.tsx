import React from "react";
import { FeedbackDetail } from "../shared/feedback/FeedbackDetail";
import { ghostButtonClass } from "@yinfengwindy/shiori-sdk";
import { errorFeedback, scrubErrorDetail } from "@yinfengwindy/shiori-sdk/host-internal";

type DesktopErrorBoundaryProps = { children: React.ReactNode };
type DesktopErrorBoundaryState = { hasError: boolean; detail: string; folderError: string; detailOpen: boolean };

/** Catches renderer failures and keeps diagnostics reachable without the app tree. */
export class DesktopErrorBoundary extends React.Component<DesktopErrorBoundaryProps, DesktopErrorBoundaryState> {
  state: DesktopErrorBoundaryState = { hasError: false, detail: "", folderError: "", detailOpen: false };

  static getDerivedStateFromError(error: Error): DesktopErrorBoundaryState {
    return { hasError: true, detail: scrubErrorDetail(error.stack || error.message), folderError: "", detailOpen: false };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    try {
      window.miraDesktop.reportRendererDiagnostic({
        kind: "error-boundary", message: scrubErrorDetail(error.message),
        stack: scrubErrorDetail(error.stack ?? ""), componentStack: info.componentStack ?? "",
      });
    } catch {
      // Reporting may fail with the renderer bridge; the fallback stays usable
      // and does not claim that a diagnostic file was successfully written.
    }
  }

  private async openLogs() {
    try {
      await window.miraDesktop.openDiagnosticsFolder();
      this.setState({ folderError: "" });
    } catch (error) {
      const failure = errorFeedback(error, "日志文件夹打开失败");
      this.setState({ folderError: [failure.message, failure.detail].filter(Boolean).join("\n") });
    }
  }

  render(): React.ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="grid h-screen place-items-center bg-gradient-app bg-fixed px-6 text-center text-ink-secondary">
        <div className="grid w-full max-w-[420px] gap-3 rounded-md border border-line-soft bg-surface px-6 py-7 shadow-soft">
          <div className="text-body font-semibold">界面暂时不可用</div>
          <p className="m-0 text-body-sm text-ink-muted">请重新打开桌面端。如果再次出现，可以查看诊断日志。</p>
          <button type="button" className={ghostButtonClass} onClick={() => void this.openLogs()}>打开日志文件夹</button>
          {this.state.folderError ? <p role="alert" className="m-0 whitespace-pre-wrap break-words text-body-sm text-danger-text">日志文件夹打开失败，请查看详情。</p> : null}
          <FeedbackDetail detail={[this.state.detail, this.state.folderError].filter(Boolean).join("\n")}
            open={this.state.detailOpen} onToggle={() => this.setState((state) => ({ detailOpen: !state.detailOpen }))} />
        </div>
      </div>
    );
  }
}
