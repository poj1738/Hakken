// The fixed disclaimer and PLAN §8's honest limits. Caveats about a particular
// result come from the API and are shown with that result instead.
export const DISCLAIMER = "Synthetic data. Not medical advice. A pharmacist must confirm every item.";

export function Footer() {
  return (
    <footer className="ft">
      <div>
        <strong>Synthetic data. Not medical advice.</strong> A pharmacist must confirm every item. Model output may vary
        between runs. Identity-matching statistics come mostly from US studies; there are no public Australian IHI match
        rates. Harm cases are illustrations.
      </div>
    </footer>
  );
}
