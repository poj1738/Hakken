/** The three-step flow at the top of the page, with the current step highlighted. */
const STEPS = ["Select patient", "Run reconciliation", "Review discrepancies"];

export function Stepper({ current, busy }: { current: 1 | 2 | 3; busy: boolean }) {
  return (
    <ol className="steps" aria-label="Progress">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const state = n < current ? "done" : n === current ? "now" : "next";
        return (
          <li key={label} className={`step step-${state}`} aria-current={state === "now" ? "step" : undefined}>
            <span className="step-num" aria-hidden>
              {state === "done" ? "✓" : n}
            </span>
            <span className="step-label">{label}</span>
            {state === "now" && busy && <span className="spinner spinner-sm" aria-label="in progress" />}
          </li>
        );
      })}
    </ol>
  );
}
