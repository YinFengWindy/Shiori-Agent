import { useEffect, useRef } from "react";
import { Check } from "@phosphor-icons/react";
import { SITE_ADV_COPY } from "../../content/siteCopy";
import { cx } from "../../siteClassNames";

export interface AdvChoiceItem {
  id: string;
  label: string;
  visited: boolean;
}

interface AdvChoiceListProps {
  choices: readonly AdvChoiceItem[];
  onChoose: (id: string) => void;
}

/**
 * Galgame choice bars. Visited topics stay selectable but are dimmed and
 * carry a check + 已读 tag. The first choice takes focus when the list
 * appears so keyboard users can pick right away.
 */
export function AdvChoiceList({ choices, onChoose }: AdvChoiceListProps) {
  const firstRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    firstRef.current?.focus();
  }, []);

  return (
    <ul aria-label={SITE_ADV_COPY.choicesLabel} className="site-adv-choices flex w-full flex-col">
      {choices.map((choice, index) => (
        <li key={choice.id} className="site-adv-choice-item" style={{ animationDelay: `${index * 40}ms` }}>
          <button
            ref={index === 0 ? firstRef : undefined}
            type="button"
            onClick={() => onChoose(choice.id)}
            className={cx("site-adv-choice flex w-full items-center justify-center gap-2 rounded-md font-display", choice.visited && "site-adv-choice-visited")}
          >
            <span>{choice.label}</span>
            {choice.visited ? (
              <span className="site-adv-choice-read inline-flex items-center gap-0.5 rounded-full">
                <Check size={12} weight="bold" aria-hidden="true" />
                {SITE_ADV_COPY.visited}
              </span>
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  );
}
