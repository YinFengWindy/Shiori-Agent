import { cx } from "@yinfengwindy/shiori-sdk";
import { ToneDot } from "./TaskStatus";
import { agentStatusLabel, agentStatusTone } from "./agentSelectors";

/** A Herdr agent state's dot followed by its label. */
export function AgentStatusLabel({ status, className }: { status: string; className?: string }) {
  return (
    <span className={cx("inline-flex shrink-0 items-center gap-1.5", className)}>
      <ToneDot tone={agentStatusTone(status)} />
      {agentStatusLabel(status)}
    </span>
  );
}
