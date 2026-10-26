import type { ReactNode } from "react";

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
        <dl>
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {children}
    </details>
  );
}
