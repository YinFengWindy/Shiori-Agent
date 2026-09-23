import { CHARACTER_PROFILE } from "../../content/characterProfile";
import { SITE_CHARACTER_COPY } from "../../content/siteCopy";

/**
 * 吟风's profile card: name plate, one-line tagline, the 身份/属性/… rows
 * and a few signature lines in her voice. Copy lives in
 * `content/characterProfile.ts`.
 */
export function CharacterProfileCard() {
  return (
    <section aria-labelledby="site-character-name" className="site-character-card flex min-h-0 flex-col rounded-xl">
      <h2 id="site-character-name" className="site-character-name font-display">
        {CHARACTER_PROFILE.name}
      </h2>
      <span className="site-ornament-line site-character-ornament" aria-hidden="true" />
      <p className="site-character-tagline">{CHARACTER_PROFILE.tagline}</p>
      <dl className="site-character-fields">
        {CHARACTER_PROFILE.fields.map((field) => (
          <div key={field.label} className="site-character-field flex min-w-0 items-baseline">
            <dt className="site-character-field-label shrink-0 font-display">{field.label}</dt>
            <dd className="min-w-0">{field.value}</dd>
          </div>
        ))}
      </dl>
      <h3 className="sr-only">{SITE_CHARACTER_COPY.lines}</h3>
      <ul className="site-character-lines flex flex-col">
        {CHARACTER_PROFILE.lines.map((line) => (
          <li key={line} className="site-character-line">
            {line}
          </li>
        ))}
      </ul>
    </section>
  );
}
