import type { MascotLine } from "../shared/mascot/mascotLines";
import { MascotEmptyState } from "../shared/mascot/MascotSpeech";
import { useMascotEnabled } from "../shared/mascot/useMascotEnabled";
import { PetalIcon } from "../shared/ui/icons";

/**
 * An empty phone screen: 吟风 with her `line` while the 看板娘 is on;
 * otherwise a petal mark and the plain `label`, with no room left for her.
 */
export function PhoneEmptyState({ line, label, testId }: { line: MascotLine; label: string; testId: string }) {
  if (useMascotEnabled()) {
    return <MascotEmptyState line={line} layout="stack" className="px-4 pt-8" testId={testId} />;
  }
  return (
    <div className="grid justify-items-center gap-3 px-4 pt-16 text-center" data-testid={testId}>
      <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent">
        <PetalIcon className="h-5 w-5" />
      </span>
      <span className="phone-glass rounded-full px-3 py-0.5 text-body-sm text-ink-muted">{label}</span>
    </div>
  );
}
