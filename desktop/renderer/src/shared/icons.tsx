type DesktopIconProps = {
  className?: string;
};

/** Renders the shared desktop loading spinner glyph. */
export function SpinnerIcon({ className = "h-4 w-4 stroke-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <circle cx="12" cy="12" r="8.5" className="opacity-20" strokeWidth="2.5" />
      <path d="M12 3.5a8.5 8.5 0 0 1 8.5 8.5" strokeLinecap="round" strokeWidth="2.5" />
    </svg>
  );
}

/** Renders the shared desktop save glyph. */
export function SaveIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M382.4 876 7.4 501 43.1 465.4 380.9 803.2 983.6 149.7 1020.7 183.9Z" />
    </svg>
  );
}

/** Renders the shared desktop reset/refresh glyph. */
export function ResetIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M958.72 225.856l-82.688 211.136-13.76 35.2c-3.776 9.728-14.784 14.528-24.512 10.688l-35.2-13.76L591.36 386.368C581.632 382.528 576.832 371.584 580.672 361.856l13.76-35.2c3.776-9.728 14.784-14.528 24.512-10.688l174.912 68.544c-50.56-124.416-171.584-212.672-314.112-212.672-187.84 0-340.16 152.32-340.16 340.16s152.256 340.16 340.16 340.16c148.032 0 273.6-94.72 320.384-226.752l79.296 0c-49.408 174.4-209.408 302.336-399.68 302.336C250.112 927.744 64 741.632 64 512s186.112-415.744 415.744-415.744c157.056 0 293.376 87.296 363.968 215.872l44.608-113.856c3.776-9.728 14.784-14.528 24.512-10.688l35.2 13.76C957.696 205.184 962.496 216.128 958.72 225.856z" />
    </svg>
  );
}

/** Renders the shared desktop delete/close glyph. */
export function DeleteIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M107.632 107.632c15.52-15.52 40.64-15.52 56.16 0L512 455.824 860.208 107.632a39.712 39.712 0 0 1 56.16 56.16L568.176 512l348.192 348.208c14.832 14.832 15.472 38.48 1.936 54.08l-1.936 2.08c-15.52 15.52-40.64 15.52-56.16 0L512 568.176 163.792 916.368a39.712 39.712 0 1 1-56.16-56.16L455.824 512 107.632 163.792a39.712 39.712 0 0 1-1.936-54.08z" />
    </svg>
  );
}

/** Renders the shared desktop upload glyph. */
export function UploadIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M323.034074 291.934815l383.620741 0c9.481481 0 17.256296-8.533333 17.256296-18.962963 0-10.42963-7.68-18.962963-17.256296-18.962963L323.034074 254.008889c-9.481481 0-17.256296 8.533333-17.256296 18.962963C305.777778 283.496296 313.457778 291.934815 323.034074 291.934815z" />
      <path d="M522.05037 328.628148c-1.232593-1.232593-2.844444-1.896296-4.740741-1.991111-1.706667-0.094815-3.318519-0.094815-5.025185 0-1.896296 0.094815-3.508148 0.758519-4.740741 1.991111L349.013333 487.253333c-3.887407 3.887407-1.896296 12.325926 4.456296 18.773333 6.447407 6.447407 14.791111 8.438519 18.773333 4.456296l125.060741-125.060741 0 367.122963c0 9.671111 7.86963 17.540741 17.540741 17.540741l0 0c9.671111 0 17.540741-7.86963 17.540741-17.540741L532.385185 385.327407l125.060741 125.060741c3.887407 3.887407 12.325926 1.896296 18.773333-4.456296 6.447407-6.447407 8.438519-14.791111 4.456296-18.773333L522.05037 328.628148z" />
    </svg>
  );
}
