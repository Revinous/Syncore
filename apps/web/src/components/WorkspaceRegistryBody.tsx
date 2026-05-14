import Link from "next/link";
import type { FormEvent } from "react";

import type { Workspace, WorkspaceFile, WorkspaceScanResult } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { PageHeader } from "./PageHeader";
import { Surface } from "./Surface";

type WorkspaceRegistryBodyProps = {
  workspaces: Workspace[];
  selectedWorkspaceId: string;
  setSelectedWorkspaceId: (value: string) => void;
  scanResult: WorkspaceScanResult | null;
  filesResult: WorkspaceFile | null;
  error: string | null;
  loading: boolean;
  refreshing: boolean;
  lastLoadedAt: Date | null;
  name: string;
  setName: (value: string) => void;
  rootPath: string;
  setRootPath: (value: string) => void;
  repoUrl: string;
  setRepoUrl: (value: string) => void;
  branch: string;
  setBranch: (value: string) => void;
  selected: Workspace | null;
  scan: WorkspaceScanResult["scan"] | null | undefined;
  freshnessState: string;
  isOfflineError: boolean | undefined;
  onLoad: () => void | Promise<void>;
  onCreateWorkspace: (event: FormEvent<HTMLFormElement>) => void | Promise<void>;
  onScan: () => void | Promise<void>;
  onListFiles: () => void | Promise<void>;
};

export function WorkspaceRegistryBody({
  workspaces,
  selectedWorkspaceId,
  setSelectedWorkspaceId,
  scanResult,
  filesResult,
  error,
  loading,
  refreshing,
  lastLoadedAt,
  name,
  setName,
  rootPath,
  setRootPath,
  repoUrl,
  setRepoUrl,
  branch,
  setBranch,
  selected,
  scan,
  freshnessState,
  isOfflineError,
  onLoad,
  onCreateWorkspace,
  onScan,
  onListFiles,
}: WorkspaceRegistryBodyProps) {
  return (
    <div className="page-shell">
      <PageHeader
        title="Workspace Registry"
        subtitle="Attach an existing project, inspect the inferred stack, and expose only the files that Syncore can safely operate against."
        kicker="Repo Attach"
        actions={
          <>
            <button className="secondary-button" onClick={() => void onLoad()}>
              Refresh List
            </button>
            <button className="button" onClick={() => void onScan()} disabled={!selectedWorkspaceId}>
              Scan Selected
            </button>
          </>
        }
        metrics={[
          { label: "Registered", value: workspaces.length },
          { label: "Selected", value: selected?.name ?? "none" },
        ]}
      />

      <div className="operator-strip">
        <div className="operator-strip-block">
          <span className="operator-strip-label">Freshness</span>
          <div className="operator-strip-value">{freshnessState}</div>
        </div>
        <div className="operator-strip-block">
          <span className="operator-strip-label">Last Refresh</span>
          <div className="operator-strip-value">
            {lastLoadedAt
              ? `${lastLoadedAt.toLocaleTimeString()}${refreshing ? " · refreshing" : ""}`
              : "waiting"}
          </div>
        </div>
        <div className="operator-strip-block">
          <span className="operator-strip-label">Cadence</span>
          <div className="operator-strip-value">auto every 20s</div>
        </div>
      </div>

      {loading && <LoadingState message="Loading workspaces..." />}
      {error && (
        <ErrorState
          title={isOfflineError ? "Syncore API offline" : "Operator attention required"}
          message={error}
          hint={
            isOfflineError
              ? "The browser cannot reach the local orchestrator. Start Syncore services, then refresh the workspace registry."
              : "Refresh the surface. If this persists, check diagnostics and service health."
          }
        />
      )}

      <div className="content-grid two-column">
        <div className="stack">
          <Surface
            title="Add Workspace"
            description="Point Syncore at a real repo or project root. Native local mode is preserved by default."
          >
            <form onSubmit={onCreateWorkspace} className="form-grid two-up">
              <label className="field-label">
                Workspace name
                <input
                  className="field"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="syncore"
                  required
                />
              </label>
              <label className="field-label">
                Branch
                <input
                  className="field"
                  value={branch}
                  onChange={(event) => setBranch(event.target.value)}
                  placeholder="main"
                />
              </label>
              <label className="field-label" style={{ gridColumn: "1 / -1" }}>
                Root path
                <input
                  className="field"
                  value={rootPath}
                  onChange={(event) => setRootPath(event.target.value)}
                  placeholder="./"
                  required
                />
              </label>
              <label className="field-label" style={{ gridColumn: "1 / -1" }}>
                Repo URL
                <input
                  className="field"
                  value={repoUrl}
                  onChange={(event) => setRepoUrl(event.target.value)}
                  placeholder="https://github.com/org/repo"
                />
              </label>
              <div className="control-row" style={{ gridColumn: "1 / -1" }}>
                <button className="button" type="submit">
                  Create Workspace
                </button>
              </div>
            </form>
          </Surface>

          <Surface
            title="Workspace Inventory"
            description="Current attached projects and their runtime mode."
            actions={
              <div className="control-row">
                <select
                  className="field"
                  value={selectedWorkspaceId}
                  onChange={(event) => setSelectedWorkspaceId(event.target.value)}
                  style={{ minWidth: 280 }}
                >
                  <option value="">Select workspace</option>
                  {workspaces.map((workspace) => (
                    <option key={workspace.id} value={workspace.id}>
                      {workspace.name} ({workspace.root_path})
                    </option>
                  ))}
                </select>
                <button
                  className="secondary-button"
                  onClick={() => void onListFiles()}
                  disabled={!selectedWorkspaceId}
                >
                  List Files
                </button>
              </div>
            }
          >
            {workspaces.length === 0 ? (
              <EmptyState message="No workspaces registered yet." />
            ) : (
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Root Path</th>
                      <th>Branch</th>
                      <th>Mode</th>
                      <th>Task Jump</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workspaces.map((workspace) => (
                      <tr key={workspace.id}>
                        <td>{workspace.name}</td>
                        <td>
                          <span className="inline-code">{workspace.root_path}</span>
                        </td>
                        <td>{workspace.branch || "-"}</td>
                        <td>{workspace.runtime_mode}</td>
                        <td>
                          <Link href={`/tasks?workspace=${workspace.id}`}>Open tasks</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Surface>
        </div>

        <div className="stack">
          <Surface
            title={selected ? `Selected Workspace: ${selected.name}` : "Selected Workspace"}
            description="Stack scan output and inferred repo-operating contract."
            tone="highlight"
          >
            {!selected ? (
              <EmptyState message="Select a workspace to inspect scan output." />
            ) : !scan ? (
              <EmptyState message="Run a scan to see detected languages, frameworks, docs, and runbook signals." />
            ) : (
              <>
                <div className="meta-grid">
                  <div className="meta-card">
                    <span className="meta-label">Languages</span>
                    <div className="meta-value">{(scan.languages || []).join(", ") || "none"}</div>
                  </div>
                  <div className="meta-card">
                    <span className="meta-label">Frameworks</span>
                    <div className="meta-value">{(scan.frameworks || []).join(", ") || "none"}</div>
                  </div>
                  <div className="meta-card">
                    <span className="meta-label">Package Managers</span>
                    <div className="meta-value">{(scan.package_managers || []).join(", ") || "none"}</div>
                  </div>
                  <div className="meta-card">
                    <span className="meta-label">Entrypoints</span>
                    <div className="meta-value">{(scan.entrypoints || []).join(", ") || "none"}</div>
                  </div>
                </div>

                <div className="panel-grid two-up" style={{ marginTop: 16 }}>
                  <div className="callout">
                    <strong>Important files</strong>
                    {(scan.important_files || []).length === 0 ? (
                      <div className="helper-text">No important files detected.</div>
                    ) : (
                      <ul className="list-reset">
                        {(scan.important_files || []).slice(0, 12).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div className="callout">
                    <strong>Docs</strong>
                    {(scan.docs || []).length === 0 ? (
                      <div className="helper-text">No docs detected.</div>
                    ) : (
                      <ul className="list-reset">
                        {(scan.docs || []).slice(0, 12).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

                <div style={{ marginTop: 16 }} className="code-block">
                  {JSON.stringify(scanResult?.scan, null, 2)}
                </div>
              </>
            )}
          </Surface>

          <Surface
            title={selected ? `Safe Files: ${selected.name}` : "Safe Files"}
            description="Only relative paths under the workspace boundary and outside blocked secret patterns are surfaced here."
          >
            {!selected ? (
              <EmptyState message="Select a workspace first." />
            ) : !filesResult ? (
              <EmptyState message="List files to inspect the safe exposure set." />
            ) : filesResult.files.length === 0 ? (
              <EmptyState message="No safe files exposed." />
            ) : (
              <>
                <div className="helper-text" style={{ marginBottom: 12 }}>
                  {filesResult.count} files available for controlled access.
                </div>
                <div className="code-block">{filesResult.files.slice(0, 200).join("\n")}</div>
              </>
            )}
          </Surface>
        </div>
      </div>
    </div>
  );
}
