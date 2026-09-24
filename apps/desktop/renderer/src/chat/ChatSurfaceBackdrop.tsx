import { CrossfadeLayers } from "../shared/CrossfadeLayers";

/**
 * The role's chat background behind the conversation, with the left-to-right
 * wash that keeps messages readable. A background change crossfades.
 */
export function ChatSurfaceBackdrop({ url }: { url: string }) {
  return (
    <div
      className="conversation-illustration pointer-events-none absolute inset-0 z-0 overflow-hidden"
      aria-hidden="true"
    >
      <CrossfadeLayers
        value={url}
        render={(layerUrl) => (
          <div
            className="conversation-illustration-image absolute inset-0 bg-cover bg-center bg-no-repeat opacity-[0.96]"
            style={{ backgroundImage: `url("${layerUrl}")` }}
          />
        )}
      />
      <div className="conversation-illustration-fade absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.78)_0%,rgba(255,255,255,0.64)_24%,rgba(255,255,255,0.4)_48%,rgba(255,255,255,0.14)_72%,rgba(255,255,255,0.03)_100%)]" />
    </div>
  );
}
