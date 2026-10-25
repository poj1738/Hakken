import { useState } from "react";

// Ticks are local to this screen; the task list itself comes from the API.
export function Tasks({ tasks }: { tasks: string[] }) {
  const [done, setDone] = useState<Record<string, boolean>>({});
  if (!tasks.length) return null;
  return (
    <section className="card tasks">
      <h2>Tasks</h2>
      <ul>
        {tasks.map((t) => (
          <li key={t}>
            <label className={done[t] ? "done" : ""}>
              <input type="checkbox" checked={!!done[t]} onChange={(e) => setDone({ ...done, [t]: e.target.checked })} /> {t}
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
