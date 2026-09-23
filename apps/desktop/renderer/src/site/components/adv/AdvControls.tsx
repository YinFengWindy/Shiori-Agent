import type { MouseEvent, ReactNode } from "react";
import { ClockCounterClockwise, FastForward, GearSix, House, Play } from "@phosphor-icons/react";
import { SITE_ADV_COPY } from "../../content/siteCopy";
import { cx } from "../../siteClassNames";

interface AdvControlsProps {
  autoMode: boolean;
  canSkip: boolean;
  onToggleAuto: () => void;
  onSkip: () => void;
  onOpenBacklog: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
}

// Mouse clicks must not park focus on a control: otherwise the next Space /
// Enter would re-press that control instead of advancing the dialogue.
// Keyboard users still Tab to the controls normally.
function keepFocus(event: MouseEvent) {
  event.preventDefault();
}

function ControlButton(props: { label: string; icon: ReactNode; onClick: () => void; pressed?: boolean; disabled?: boolean; ariaLabel?: string }) {
  return (
    <button
      type="button"
      onMouseDown={keepFocus}
      onClick={props.onClick}
      disabled={props.disabled}
      aria-pressed={props.pressed}
      aria-label={props.ariaLabel}
      className={cx("site-adv-control inline-flex items-center gap-1 rounded-md", props.pressed && "site-adv-control-active")}
    >
      {props.icon}
      <span>{props.label}</span>
    </button>
  );
}

/** 自动 / 跳过 / 记录 / 设置 / 标题 buttons in the dialogue box. */
export function AdvControls(props: AdvControlsProps) {
  return (
    <>
      <ControlButton label={SITE_ADV_COPY.auto} icon={<Play size={14} weight={props.autoMode ? "fill" : "regular"} aria-hidden="true" />} pressed={props.autoMode} onClick={props.onToggleAuto} />
      <ControlButton label={SITE_ADV_COPY.skip} icon={<FastForward size={14} aria-hidden="true" />} disabled={!props.canSkip} onClick={props.onSkip} />
      <ControlButton label={SITE_ADV_COPY.backlog} icon={<ClockCounterClockwise size={14} aria-hidden="true" />} onClick={props.onOpenBacklog} />
      <ControlButton label={SITE_ADV_COPY.settings} icon={<GearSix size={14} aria-hidden="true" />} onClick={props.onOpenSettings} />
      <ControlButton label={SITE_ADV_COPY.title} ariaLabel={SITE_ADV_COPY.titleLabel} icon={<House size={14} aria-hidden="true" />} onClick={props.onExit} />
    </>
  );
}
