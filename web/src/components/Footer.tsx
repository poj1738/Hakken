export function Footer({ caveats }: { caveats: string[] }) {
  const extra = caveats.filter((c) => !c.startsWith("Synthetic data. Not medical advice"));
  return (
    <footer className="footer">
      <p className="disclaimer">
        <strong>Synthetic data. Not medical advice. A pharmacist must confirm every item.</strong>
      </p>
      <p className="small muted">
        Model output can vary between runs. Identity-matching statistics come mostly from US studies; there are no public
        Australian IHI match rates. Harm cases are illustrations.
      </p>
      {extra.map((c) => (
        <p key={c} className="small muted">
          {c}
        </p>
      ))}
    </footer>
  );
}
