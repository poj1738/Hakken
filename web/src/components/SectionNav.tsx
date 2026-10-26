import type { KeyboardEvent } from "react";

export interface NavItem<T extends string> {
  id: T;
  label: string;
  /** A live count from the API response (or the on-screen checklist); null shows none. */
  count: number | null;
  /** Draws the count in the alert colour (e.g. high-alert items waiting). */
  alert?: boolean;
  disabled?: boolean;
}

/**
 * The workspace's left rail: one link per section, each with its live count.
 * It behaves as a vertical tab list (arrow keys move between sections); choosing
 * one shows that section and scrolls it into view.
 */
export function SectionNav<T extends string>({ items, current, onSelect, panelId }: { items: NavItem<T>[]; current: T; onSelect: (id: T) => void; panelId: string }) {
  const enabled = items.filter((i) => !i.disabled);
  const move = (e: KeyboardEvent<HTMLButtonElement>, id: T) => {
    const at = enabled.findIndex((i) => i.id === id);
    let next = -1;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") next = (at + 1) % enabled.length;
    if (e.key === "ArrowUp" || e.key === "ArrowLeft") next = (at - 1 + enabled.length) % enabled.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = enabled.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onSelect(enabled[next].id);
    document.getElementById(`nav-${enabled[next].id}`)?.focus();
  };
  return (
    <nav className="snav" aria-label="Sections">
      <div role="tablist" aria-orientation="vertical" className="snav-list">
        {items.map((i) => (
          <button
            key={i.id}
            id={`nav-${i.id}`}
            type="button"
            role="tab"
            aria-selected={current === i.id}
            aria-controls={panelId}
            tabIndex={current === i.id ? 0 : -1}
            disabled={i.disabled}
            className={`snav-item ${current === i.id ? "on" : ""}`}
            onClick={() => onSelect(i.id)}
            onKeyDown={(e) => move(e, i.id)}
          >
            <span>{i.label}</span>
            {i.count !== null && <span className={`snav-count ${i.alert ? "snav-alert" : ""}`}>{i.count}</span>}
          </button>
        ))}
      </div>
    </nav>
  );
}
