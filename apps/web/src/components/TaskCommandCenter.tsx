type TaskCommandCenterProps = {
  commandPrompt: string;
  onCommandPromptChange: (value: string) => void;
  onExecuteTask: () => void | Promise<void>;
  onStartRun: () => void | Promise<void>;
  onRouteTask: () => void | Promise<void>;
  onGenerateDigest: () => void | Promise<void>;
  onRefresh: () => void | Promise<void>;
  runningAction: string | null;
  actionMessage: string | null;
  disabled?: boolean;
};

export function TaskCommandCenter({
  commandPrompt,
  onCommandPromptChange,
  onExecuteTask,
  onStartRun,
  onRouteTask,
  onGenerateDigest,
  onRefresh,
  runningAction,
  actionMessage,
  disabled = false,
}: TaskCommandCenterProps) {
  return (
    <div className="stack">
      <label className="field-label">
        Execution prompt
        <textarea
          className="field"
          rows={4}
          value={commandPrompt}
          onChange={(event) => onCommandPromptChange(event.target.value)}
          placeholder="Describe exactly what Syncore should execute for this task."
        />
      </label>
      <div className="page-actions">
        <button
          className="button"
          onClick={() => void onExecuteTask()}
          disabled={disabled || runningAction !== null || !commandPrompt.trim()}
        >
          {runningAction === "execute" ? "Executing..." : "Execute Task"}
        </button>
        <button
          className="secondary-button"
          onClick={() => void onStartRun()}
          disabled={disabled || runningAction !== null}
        >
          {runningAction === "start-run" ? "Creating..." : "Start Agent Run"}
        </button>
        <button
          className="secondary-button"
          onClick={() => void onRouteTask()}
          disabled={disabled || runningAction !== null}
        >
          {runningAction === "route" ? "Routing..." : "Route Next Action"}
        </button>
        <button
          className="secondary-button"
          onClick={() => void onGenerateDigest()}
          disabled={disabled || runningAction !== null}
        >
          {runningAction === "digest" ? "Generating..." : "Generate Digest"}
        </button>
        <button
          className="ghost-button"
          onClick={() => void onRefresh()}
          disabled={runningAction !== null}
        >
          Refresh
        </button>
      </div>
      {actionMessage ? <div className="helper-text">{actionMessage}</div> : null}
    </div>
  );
}
