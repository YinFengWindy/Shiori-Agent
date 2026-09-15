import { Component, type ReactNode } from "react";
import { SurfaceFailure } from "./SurfaceFailure";
import type { SurfaceHandle } from "./pluginSurfaceRegistry";

/** Contains plugin render and mount-effect errors inside their surface window. */
export class SurfaceErrorBoundary extends Component<{
  surface: SurfaceHandle;
  children: ReactNode;
}, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  componentDidCatch(error: Error) { console.error("[surface] 插件组件挂载失败", error); }

  render() {
    return this.state.failed
      ? <SurfaceFailure detail="插件组件挂载失败" surface={this.props.surface} />
      : this.props.children;
  }
}
