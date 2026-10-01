import { createContext, useContext } from "react";
import { createPortal } from "react-dom";
import type { AccountDetailActionsProps } from "@shiori/sdk";
import { SpinnerIcon } from "../shared/icons";
import { compactTextButtonClass } from "../shared/styles";

const ActionsTargetContext = createContext<HTMLElement | null>(null);

/**
 * Where `AccountDetailActions` land: the account dialog provides the element
 * at the left of its danger zone. Tests provide any element.
 */
export const AccountDetailActionsTarget = ActionsTargetContext.Provider;

/**
 * A plugin's secondary account actions (`PluginHostServices.ui.AccountDetailActions`).
 * Rendered from inside the plugin's own detail component — so they keep its
 * state — but shown in the host's bottom danger zone, left of 删除账号, as
 * quiet text buttons. Outside an account dialog they render nothing.
 */
export function AccountDetailActions({ actions }: AccountDetailActionsProps) {
  const target = useContext(ActionsTargetContext);
  if (!target || !actions.length) return null;
  return createPortal(actions.map(({ label, onClick, icon: Icon, pending = false, disabled = false }) => (
    <button key={label} type="button" className={compactTextButtonClass}
      disabled={pending || disabled} aria-busy={pending || undefined} onClick={onClick}>
      {pending
        ? <SpinnerIcon className="h-4 w-4 animate-spin stroke-current motion-reduce:animate-none" />
        : Icon ? <Icon className="h-4 w-4" /> : null}
      {label}
    </button>
  )), target);
}
