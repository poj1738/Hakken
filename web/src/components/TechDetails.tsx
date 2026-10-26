import { useState, type ReactNode } from "react";

/** An identifier on one line: truncated with an ellipsis if long, full value in the tooltip, and a Copy button. */
function CopyId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (e.g. an insecure origin): the value stays selectable in the tooltip.
    }
  };
  return (
    <span className="copy-id">
      <span className="copy-val" title={value}>
        {value}
      </span>
      <button type="button" className="copy-btn" onClick={copy} aria-label={`Copy ${value}`}>
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}

// One token, no spaces, long enough to be worth copying: a query id, record key, file path.
const isId = (v: ReactNode): v is string => typeof v === "string" && !/\s/.test(v) && v.length > 20;

/**
 * The one place internal identifiers live: record keys, row ids, query ids,
 * template ids, tool names, raw API text. Collapsed by default so the main view
 * reads cleanly; one click away so every piece of provenance stays reachable.
 */
export function TechDetails({
  items,
  children,
  label = "Technical details",
}: {
  items?: [string, ReactNode][];
  children?: ReactNode;
  label?: string;
}) {
  const rows = (items ?? []).filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && !v.length));
  if (!rows.length && !children) return null;
  return (
    <details className="tech">
      <summary>{label}</summary>
      {rows.length > 0 && (
        <dl className="tech-dl">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{isId(v) ? <CopyId value={v} /> : v}</dd>
            </div>
          ))}
        </dl>
      )}
      {children}
    </details>
  );
}
