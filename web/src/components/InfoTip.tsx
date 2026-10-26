import { useId } from "react";

/**
 * A small "i" that shows explanatory text on hover or keyboard focus. The text
 * that used to be a visible subtitle lives here, so the main view stays short
 * and nothing is lost. The button is focusable and names its text for screen
 * readers; the bubble is hidden (display: none) until hover or focus.
 */
export function InfoTip({ text, label = "More information" }: { text: string; label?: string }) {
  const id = useId();
  return (
    <span className="tip">
      <button type="button" className="tip-btn" aria-label={label} aria-describedby={id}>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
          <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <path d="M8 7v4.5M8 4.6v.1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
      <span role="tooltip" id={id} className="tip-box">
        {text}
      </span>
    </span>
  );
}
