import type { AgentRun, TaskDetail } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { StatusBadge } from "./StatusBadge";
import { Surface } from "./Surface";

type TaskContextPanelsProps = {
  detail: TaskDetail;
};

export function TaskContextPanels({ detail }: TaskContextPanelsProps) {
  return (
    <>
      <Surface title="Task Overview" description="Core task metadata and current execution posture.">
        <div className="meta-grid">
          <div className="meta-card"><span className="meta-label">Task ID</span><div className="meta-value">{detail.task.id}</div></div>
          <div className="meta-card"><span className="meta-label">Task Type</span><div className="meta-value">{detail.task.task_type}</div></div>
          <div className="meta-card"><span className="meta-label">Complexity</span><div className="meta-value">{detail.task.complexity}</div></div>
          <div className="meta-card"><span className="meta-label">Status</span><div className="meta-value"><StatusBadge status={detail.task.status} /></div></div>
        </div>
      </Surface>

      <Surface title="Agent Runs" description="Runs already attached to this task.">
        {detail.agent_runs.length === 0 ? (
          <EmptyState
            message="No runs are attached to this task yet."
            hint="Start an agent run or execute the task to generate output, verification results, and artifacts."
          />
        ) : (
          <div className="stack">
            {detail.agent_runs.map((run: AgentRun) => (
              <div className="meta-card" key={run.id}>
                <span className="meta-label">{run.role}</span>
                <div className="meta-value"><StatusBadge status={run.status} /></div>
                <div className="helper-text" style={{ marginTop: 8 }}>
                  {run.output_summary ?? run.error_message ?? "No output summary recorded yet."}
                </div>
              </div>
            ))}
          </div>
        )}
      </Surface>
    </>
  );
}
