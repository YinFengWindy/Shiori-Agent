import type { ReactNode } from "react";
import { toFileUrl } from "../shared/format";

/**
 * The inside of a round phone avatar: the cached platform picture filling
 * its circle, or `placeholder` (an icon) when none is cached. The circle
 * itself (size, colors, button or not) belongs to the caller, which must clip
 * it (`overflow-hidden rounded-full`).
 */
export function PhoneAvatarFace({ avatarPath, placeholder }: {
  /** Local file of the cached avatar; null when there is none. */
  avatarPath: string | null;
  placeholder: ReactNode;
}) {
  return avatarPath
    ? <img src={toFileUrl(avatarPath)} alt="" className="h-full w-full object-cover" />
    : placeholder;
}
