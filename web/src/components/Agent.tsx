/**
 * One colour per agent, used wherever an agent is named (processing log,
 * Powered by, model-call tables). Always a coloured dot plus the agent's name,
 * never colour alone. Each dot has at least 3:1 contrast on white.
 */
export const AGENT_COLOR: Record<string, string> = {
  Planner: "#7c3aed",
  Executor: "#0369a1",
  Evaluator: "#b45309",
  Writer: "#be185d",
};

export function AgentTag({ name, small = false }: { name: string; small?: boolean }) {
  const color = AGENT_COLOR[name];
  if (!color) return <span className={`agent agent-other ${small ? "agent-sm" : ""}`}>{name}</span>;
  return (
    <span className={`agent ${small ? "agent-sm" : ""}`}>
      <span className="agent-dot" style={{ background: color }} aria-hidden />
      {name}
    </span>
  );
}
