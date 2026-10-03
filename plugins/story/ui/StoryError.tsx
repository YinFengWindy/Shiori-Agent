import { usePluginHostServices, type HostInlineErrorProps } from "@yinfengwindy/shiori-sdk";

/** Presents Story failures through the host's shared, collapsed diagnostic disclosure. */
export function StoryError(props: Pick<HostInlineErrorProps, "message" | "detail" | "className">) {
  const host = usePluginHostServices();
  return <host.ui.InlineError {...props} persona={false} />;
}
