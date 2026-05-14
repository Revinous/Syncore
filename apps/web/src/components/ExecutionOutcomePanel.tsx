import { EmptyState } from "./EmptyState";
import { StatusBadge } from "./StatusBadge";
import type { ContextReference, TaskExecutionReport } from "../lib/types";

type ExecutionOutcomePanelProps = {
  executionReport: TaskExecutionReport | null;
  selectedReference: ContextReference | null;
  loadingReferenceId: string | null;
  onOpenReference: (refId: string) => void | Promise<void>;
  onCopyValue: (value: string) => void | Promise<void>;
  onCloseReference: () => void;
};

export function ExecutionOutcomePanel({
  executionReport,
  selectedReference,
  loadingReferenceId,
  onOpenReference,
  onCopyValue,
  onCloseReference,
}: ExecutionOutcomePanelProps) {
  if (!executionReport) {
    return (
      <EmptyState
        message="No execution report was persisted for this task yet."
        hint="Execution reports appear after workspace execution or run completion and consolidate outputs, diffs, and verification."
      />
    );
  }

  return (
    <div className="stack">
      <div className="outcome-grid">
        <div className="meta-card">
          <span className="meta-label">Outcome</span>
          <div className="meta-value"><StatusBadge status={executionReport.outcome_status} /></div>
        </div>
        <div className="meta-card">
          <span className="meta-label">Meaningful Change</span>
          <div className="meta-value">{executionReport.meaningful_change ? "yes" : "no"}</div>
        </div>
        <div className="meta-card">
          <span className="meta-label">Verification</span>
          <div className="meta-value">{executionReport.verification_status ?? "n/a"}</div>
        </div>
        <div className="meta-card">
          <span className="meta-label">Updated</span>
          <div className="meta-value">
            {executionReport.last_updated_at
              ? new Date(executionReport.last_updated_at).toLocaleString()
              : "n/a"}
          </div>
        </div>
      </div>

      <div className="callout">
        <p className="callout-title">Why it ended this way</p>
        <p className="callout-copy">{executionReport.summary_reason}</p>
        {executionReport.verification_reason ? (
          <div className="helper-text" style={{ marginTop: 8 }}>
            {executionReport.verification_reason}
          </div>
        ) : null}
      </div>

      <div className="panel-grid two-up">
        <div className="callout">
          <p className="callout-title">Changed Files</p>
          {executionReport.changed_files.length === 0 ? (
            <div className="helper-text">No changed files recorded.</div>
          ) : (
            <ul className="list-reset">
              {executionReport.changed_files.map((item) => <li key={item}>{item}</li>)}
            </ul>
          )}
        </div>
        <div className="callout">
          <p className="callout-title">Planned Actions</p>
          {executionReport.planned_actions.length === 0 ? (
            <div className="helper-text">No planned actions recorded.</div>
          ) : (
            <ul className="list-reset">
              {executionReport.planned_actions.map((item, index) => (
                <li key={`${index}-${item}`}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {executionReport.output_artifacts.length > 0 ? (
        <div className="callout">
          <p className="callout-title">Latest Output Summary</p>
          <p className="callout-copy">
            {executionReport.output_artifacts[0]?.output_preview || "No output preview recorded."}
          </p>
        </div>
      ) : null}

      <div className="panel-grid two-up">
        <div className="surface inset">
          <div className="section-header">
            <div>
              <h3 className="section-title">Verification Commands</h3>
              <p className="section-copy">Command execution status and output excerpts.</p>
            </div>
          </div>
          {executionReport.verification_commands.length === 0 ? (
            <EmptyState
              message="No verification command results were persisted for this task."
              hint="Once verification runs are captured, this panel shows which commands passed or failed and why."
            />
          ) : (
            <div className="stack">
              {executionReport.verification_commands.map((item, index) => (
                <details className="artifact-details" key={`${index}-${item.command}`}>
                  <summary className="artifact-summary">
                    <div className="artifact-summary-row">
                      <div className="artifact-summary-copy">
                        <div className="artifact-summary-title">
                          <span className="inline-code">{item.command}</span>
                        </div>
                        <div className="artifact-summary-meta">
                          Verification command output and status.
                        </div>
                      </div>
                      <StatusBadge status={item.status} />
                    </div>
                  </summary>
                  <div className="artifact-body">
                    {item.output_preview ? (
                      <div className="code-block">{item.output_preview}</div>
                    ) : (
                      <div className="helper-text">No output preview was captured.</div>
                    )}
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>

        <div className="surface inset">
          <div className="section-header">
            <div>
              <h3 className="section-title">Run Outputs</h3>
              <p className="section-copy">What each run returned or why it failed.</p>
            </div>
          </div>
          {executionReport.output_artifacts.length === 0 ? (
            <EmptyState
              message="No run outputs were recorded for this task."
              hint="Run outputs appear here after a worker produces an output summary or a captured failure message."
            />
          ) : (
            <div className="stack">
              {executionReport.output_artifacts.map((item) => {
                const outputRefId = item.output_ref_id;
                return (
                  <details className="artifact-details" key={item.run_id}>
                    <summary className="artifact-summary">
                      <div className="artifact-summary-row">
                        <div className="artifact-summary-copy">
                          <div className="artifact-summary-title">{item.role}</div>
                          <div className="artifact-summary-meta">
                            {item.provider ?? "unknown"} · {item.target_model ?? "unknown"} ·{" "}
                            {new Date(item.updated_at).toLocaleString()}
                          </div>
                        </div>
                        <StatusBadge status={item.status} />
                      </div>
                    </summary>
                    <div className="artifact-body">
                      <div className="page-actions" style={{ marginBottom: 10 }}>
                        {outputRefId ? (
                          <>
                            <button
                              className="secondary-button"
                              onClick={() => void onOpenReference(outputRefId)}
                              disabled={loadingReferenceId === outputRefId}
                            >
                              {loadingReferenceId === outputRefId ? "Loading..." : "Open Full Output"}
                            </button>
                            <button
                              className="ghost-button"
                              onClick={() => void onCopyValue(outputRefId)}
                            >
                              Copy Ref ID
                            </button>
                          </>
                        ) : null}
                      </div>
                      <div className="helper-text">
                        Run ID: <span className="inline-code">{item.run_id}</span>
                      </div>
                      {outputRefId ? (
                        <div className="helper-text">
                          Output ref: <span className="inline-code">{outputRefId}</span>
                        </div>
                      ) : null}
                      {item.error_message ? <div className="error-state">{item.error_message}</div> : null}
                      {item.output_preview ? (
                        <div className="code-block">{item.output_preview}</div>
                      ) : (
                        <div className="helper-text">No output preview was captured.</div>
                      )}
                    </div>
                  </details>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="surface inset">
        <div className="section-header">
          <div>
            <h3 className="section-title">File Diffs</h3>
            <p className="section-copy">
              Persisted diff artifacts stored by Syncore during workspace execution.
            </p>
          </div>
        </div>
        {executionReport.diff_artifacts.length === 0 ? (
          <EmptyState
            message="No diff artifacts were recorded for this task."
            hint="When workspace execution stores file diffs, you can inspect the persisted previews here."
          />
        ) : (
          <div className="stack">
            {executionReport.diff_artifacts.map((artifact) => (
              <details className="artifact-details" key={artifact.ref_id}>
                <summary className="artifact-summary">
                  <div className="artifact-summary-row">
                    <div className="artifact-summary-copy">
                      <div className="artifact-summary-title">{artifact.path}</div>
                      <div className="artifact-summary-meta">{artifact.summary}</div>
                    </div>
                    <span className="label-chip">{artifact.content_type}</span>
                  </div>
                </summary>
                <div className="artifact-body">
                  <div className="page-actions" style={{ marginBottom: 10 }}>
                    <button
                      className="secondary-button"
                      onClick={() => void onOpenReference(artifact.ref_id)}
                      disabled={loadingReferenceId === artifact.ref_id}
                    >
                      {loadingReferenceId === artifact.ref_id ? "Loading..." : "Open Full Artifact"}
                    </button>
                    <button className="ghost-button" onClick={() => void onCopyValue(artifact.ref_id)}>
                      Copy Ref ID
                    </button>
                  </div>
                  <div className="helper-text">
                    Ref: <span className="inline-code">{artifact.ref_id}</span>
                  </div>
                  <div className="helper-text">{artifact.retrieval_hint}</div>
                  <div className="code-block">{artifact.preview}</div>
                </div>
              </details>
            ))}
          </div>
        )}
      </div>

      {selectedReference ? (
        <div className="surface inset">
          <div className="section-header">
            <div>
              <h3 className="section-title">Retrieved Reference</h3>
              <p className="section-copy">
                Full stored content for the selected diff, output, or context artifact.
              </p>
            </div>
            <div className="page-actions">
              <button className="ghost-button" onClick={onCloseReference}>Close</button>
              <button className="secondary-button" onClick={() => void onCopyValue(selectedReference.ref_id)}>
                Copy Ref ID
              </button>
            </div>
          </div>
          <div className="helper-text" style={{ marginBottom: 8 }}>
            {selectedReference.content_type} · {selectedReference.retrieval_hint}
          </div>
          <div className="helper-text" style={{ marginBottom: 8 }}>
            Ref: <span className="inline-code">{selectedReference.ref_id}</span>
          </div>
          <div className="code-block">{selectedReference.original_content}</div>
        </div>
      ) : null}
    </div>
  );
}
