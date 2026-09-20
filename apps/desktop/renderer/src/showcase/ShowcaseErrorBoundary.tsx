import { Component, type ReactNode } from "react";
import { primaryButtonClass } from "../shared/styles";

/** Show a recoverable page when browser storage access or a demo view cannot initialize. */
export class ShowcaseErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  render() {
    if (!this.state.failed) return this.props.children;
    return <main className="grid h-dvh place-content-center gap-4 bg-surface-app p-6 text-ink" role="alert">
      <h1 className="text-title font-semibold">暂时无法打开演示</h1>
      <p className="text-body text-ink-muted">请允许浏览器访问此站点的本地存储，再重新打开页面。</p>
      <button type="button" className={primaryButtonClass} onClick={() => location.reload()}>重新打开</button>
    </main>;
  }
}
