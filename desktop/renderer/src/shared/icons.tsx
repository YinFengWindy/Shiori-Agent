import React from "react";

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

/** Renders the shared desktop locate/target glyph. */
export function LocateIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M512 102.4c-212.48 0-384 171.52-384 384s171.52 384 384 384 384-171.52 384-384-171.52-384-384-384z m25.6 716.8v-128c0-15.36-10.24-25.6-25.6-25.6s-25.6 10.24-25.6 25.6v128C322.56 806.4 192 675.84 179.2 512h128c15.36 0 25.6-10.24 25.6-25.6s-10.24-25.6-25.6-25.6h-128C192 296.96 322.56 166.4 486.4 156.16V281.6c0 15.36 10.24 25.6 25.6 25.6s25.6-10.24 25.6-25.6V156.16C701.44 168.96 832 299.52 844.8 460.8h-128c-15.36 0-25.6 10.24-25.6 25.6s10.24 25.6 25.6 25.6h128C832 675.84 701.44 806.4 537.6 819.2z" />
    </svg>
  );
}

/** Renders the shared desktop send glyph. */
export function SendIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M392.021333 925.013333a34.133333 34.133333 0 0 1-34.133333-34.133333V579.242667c0-10.24 4.608-19.968 12.629333-26.453334l276.48-224.085333a34.0992 34.0992 0 0 1 43.008 52.906667L426.154667 595.456v192.853333l82.944-110.592c10.069333-13.482667 28.672-17.578667 43.52-9.557333l137.557333 73.728L853.333333 156.16c3.242667-11.434667-3.413333-18.602667-6.485333-21.162667-3.072-2.56-11.093333-7.850667-21.845333-2.901333L206.336 422.4l80.213333 46.08c16.384 9.386667 22.016 30.208 12.629334 46.592s-30.208 22.016-46.592 12.629333l-137.045334-78.677333a33.979733 33.979733 0 0 1-17.066666-31.061333c0.512-12.8 8.021333-24.064 19.626666-29.525334L795.989333 70.314667c31.744-14.848 68.096-10.069333 94.890667 12.629333a87.790933 87.790933 0 0 1 28.16 91.477333L744.277333 801.28a34.082133 34.082133 0 0 1-48.981333 20.821333L546.133333 742.058667l-126.805333 169.301333c-6.656 8.704-16.896 13.653333-27.306667 13.653333z" />
    </svg>
  );
}

/** Renders the shared desktop plus glyph used by chat attachment creation actions. */
export function PlusIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M847.0528 491.52H532.48V176.9472c0-11.264-9.216-20.48-20.48-20.48s-20.48 9.216-20.48 20.48V491.52H176.9472c-11.264 0-20.48 9.216-20.48 20.48s9.216 20.48 20.48 20.48H491.52v314.5728c0 11.264 9.216 20.48 20.48 20.48s20.48-9.216 20.48-20.48V532.48h314.5728c11.264 0 20.48-9.216 20.48-20.48s-9.216-20.48-20.48-20.48z" />
    </svg>
  );
}

/** Renders the shared desktop back-navigation glyph. */
export function BackIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M631.04 161.941333a42.666667 42.666667 0 0 1 63.061333 57.386667l-2.474666 2.730667-289.962667 292.245333 289.706667 287.402667a42.666667 42.666667 0 0 1 2.730666 57.6l-2.474666 2.752a42.666667 42.666667 0 0 1-57.6 2.709333l-2.752-2.474667-320-317.44a42.666667 42.666667 0 0 1-2.709334-57.6l2.474667-2.752 320-322.56z" />
    </svg>
  );
}

/** Renders the shared desktop right-facing caret glyph. */
export function CaretRightIcon({ className = "h-4 w-4 stroke-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  );
}

/** Renders the shared desktop close glyph. */
export function CloseIcon({ className = "h-4 w-4 stroke-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <path d="m7 7 10 10M17 7 7 17" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

/** Renders the shared desktop smiley glyph used by chat emoji actions. */
export function SmileyIcon({ className = "h-4 w-4 stroke-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <circle cx="12" cy="12" r="8.5" strokeWidth="1.7" />
      <path d="M9.25 9.5h.01" strokeLinecap="round" strokeWidth="2.4" />
      <path d="M14.75 9.5h.01" strokeLinecap="round" strokeWidth="2.4" />
      <path d="M8.75 13.75c.8 1.2 2.1 1.75 3.25 1.75s2.45-.55 3.25-1.75" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

/** Renders the shared desktop document glyph. */
export function DocumentIcon({ className = "h-4 w-4 stroke-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <rect x="5" y="3.5" width="14" height="17" rx="3.25" strokeWidth="1.7" />
      <path d="M9 9.25h6" strokeLinecap="round" strokeWidth="1.7" />
      <path d="M9 13h6" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

/** Renders the shared desktop copy glyph. */
export function CopyIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M337.28 138.688a27.968 27.968 0 0 0-27.968 27.968v78.72h377.344c50.816 0 92.032 41.152 92.032 91.968v377.344h78.656a28.032 28.032 0 0 0 27.968-28.032V166.656a28.032 28.032 0 0 0-27.968-27.968H337.28z m441.408 640v78.656c0 50.816-41.216 91.968-92.032 91.968H166.656a92.032 92.032 0 0 1-91.968-91.968V337.28c0-50.816 41.152-92.032 91.968-92.032h78.72V166.656c0-50.816 41.152-91.968 91.968-91.968h520c50.816 0 91.968 41.152 91.968 91.968v520c0 50.816-41.152 92.032-91.968 92.032h-78.72zM166.656 309.312a27.968 27.968 0 0 0-27.968 28.032v520c0 15.424 12.544 27.968 27.968 27.968h520a28.032 28.032 0 0 0 28.032-27.968V337.28a28.032 28.032 0 0 0-28.032-28.032H166.656z" />
    </svg>
  );
}

/** Renders the shared desktop quote glyph. */
export function QuoteIcon({ className = "h-4 w-4 fill-current" }: DesktopIconProps) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} aria-hidden="true">
      <path d="M128 472.896h341.344v341.344H128zM128 472.896L272.096 192h110.08l-144.128 280.896z" />
      <path d="M544 472.896h341.344v341.344H544zM544 472.896L688.096 192h110.08l-144.128 280.896z" />
    </svg>
  );
}
