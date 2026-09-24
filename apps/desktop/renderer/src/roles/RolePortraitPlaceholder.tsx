import { toFileUrl } from "../shared/format";
import { PetalIcon, RibbonIcon, SparkleIcon } from "../shared/ui/icons";

type RolePortraitPlaceholderProps = {
  avatarPath: string;
  initial: string;
  name: string;
};

/**
 * Stands in for a missing portrait: the role's avatar (or initial) large on
 * the soft brand gradient, with a few brand motifs scattered around it, so a
 * card without art still reads as a character rather than an empty box.
 */
export function RolePortraitPlaceholder({ avatarPath, initial, name }: RolePortraitPlaceholderProps) {
  return (
    <div className="absolute inset-0 bg-gradient-accent-soft" data-testid="role-portrait-placeholder">
      <SparkleIcon className="absolute left-[14%] top-[16%] h-6 w-6 text-accent-text opacity-40" />
      <PetalIcon className="absolute right-[16%] top-[30%] h-5 w-5 rotate-12 text-accent-text opacity-35" />
      <RibbonIcon className="absolute bottom-[34%] left-[18%] h-6 w-6 -rotate-12 text-lavender-text opacity-35" />
      <SparkleIcon className="absolute bottom-[40%] right-[20%] h-4 w-4 text-lavender-text opacity-40" />
      <div className="absolute inset-x-0 top-[18%] grid place-items-center">
        {avatarPath ? (
          <img
            className="h-28 w-28 rounded-full border-4 border-white/85 object-cover shadow-panel"
            src={toFileUrl(avatarPath)}
            alt={`${name} 的头像`}
          />
        ) : (
          <span className="grid h-28 w-28 place-items-center rounded-full border-4 border-white/85 bg-gradient-accent font-display text-display text-ink shadow-panel" aria-hidden="true">
            {initial}
          </span>
        )}
      </div>
    </div>
  );
}
