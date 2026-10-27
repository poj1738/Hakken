// The fixed disclaimer, one line. PLAN §8's limitations are on the Welcome page;
// caveats about a particular result come from the API and sit with that result.
export const DISCLAIMER = "Synthetic data. Not medical advice. A pharmacist must confirm every item.";

export function Footer() {
  return (
    <footer className="ft">
      <strong>Synthetic data. Not medical advice.</strong> A pharmacist must confirm every item.
    </footer>
  );
}
