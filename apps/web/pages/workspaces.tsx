import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  createWorkspace,
  listWorkspaceFiles,
  listWorkspaces,
  scanWorkspace,
} from "../src/lib/api";
import { Workspace, WorkspaceFile, WorkspaceScanResult } from "../src/lib/types";
import { EmptyState } from "../src/components/EmptyState";
import { ErrorState } from "../src/components/ErrorState";
import { Layout } from "../src/components/Layout";
import { LoadingState } from "../src/components/LoadingState";
import { PageHeader } from "../src/components/PageHeader";
import { Surface } from "../src/components/Surface";

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>("");
  const [scanResult, setScanResult] = useState<WorkspaceScanResult | null>(null);
  const [filesResult, setFilesResult] = useState<WorkspaceFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState("syncore");
  const [rootPath, setRootPath] = useState("./");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");

  const selected = useMemo(
    () => workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ?? null,
    [workspaces, selectedWorkspaceId]
  );

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const nextWorkspaces = await listWorkspaces();
      setWorkspaces(nextWorkspaces);
      if (!selectedWorkspaceId && nextWorkspaces.length > 0) {
        setSelectedWorkspaceId(nextWorkspaces[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workspaces");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function onCreateWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      const created = await createWorkspace({
        name,
        root_path: rootPath,
        repo_url: repoUrl || null,
        branch: branch || null,
      });
      setSelectedWorkspaceId(created.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    }
  }

  async function onScan() {
    if (!selectedWorkspaceId) return;
    setError(null);
    try {
      setScanResult(await scanWorkspace(selectedWorkspaceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to scan workspace");
    }
  }

  async function onListFiles() {
    if (!selectedWorkspaceId) return;
    setError(null);
    try {
      setFilesResult(await listWorkspaceFiles(selectedWorkspaceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workspace files");
    }
  }

  const scan = scanResult?.scan;

  return (
    <Layout title="Workspaces">
      <div className="page-shell">
        <PageHeader
          title="Workspace Registry"
          subtitle="Attach an existing project, inspect the inferred stack, and expose only the files that Syncore can safely operate against."
          kicker="Repo Attach"
          actions={
            <>
              <button className="secondary-button" onClick={() => void load()}>Refresh List</button>
              <button className="button" onClick={() => void onScan()} disabled={!selectedWorkspaceId}>Scan Selected</button>
            </>
          }
          metrics={[
            { label: "Registered", value: workspaces.length },
            { label: "Selected", value: selected?.name ?? "none" },
          ]}
        />

        {loading && <LoadingState message="Loading workspaces..." />}
        {error && <ErrorState message={error} />}

        <div className="content-grid two-column">
          <div className="stack">
            <Surface
              title="Add Workspace"
              description="Point Syncore at a real repo or project root. Native local mode is preserved by default."
            >
              <form onSubmit={onCreateWorkspace} className="form-grid two-up">
                <label className="field-label">
                  Workspace name
                  <input className="field" value={name} onChange={(event) => setName(event.target.value)} placeholder="syncore" required />
                </label>
                <label className="field-label">
                  Branch
                  <input className="field" value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="main" />
                </label>
                <label className="field-label" style={{ gridColumn: "1 / -1" }}>
                  Root path
                  <input className="field" value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="./" required />
                </label>
                <label className="field-label" style={{ gridColumn: "1 / -1" }}>
                  Repo URL
                  <input className="field" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} placeholder="https://github.com/org/repo" />
                </label>
                <div className="control-row" style={{ gridColumn: "1 / -1" }}>
                  <button className="button" type="submit">Create Workspace</button>
                </div>
              </form>
            </Surface>

            <Surface
              title="Workspace Inventory"
              description="Current attached projects and their runtime mode."
              actions={
                <div className="control-row">
                  <select className="field" value={selectedWorkspaceId} onChange={(event) => setSelectedWorkspaceId(event.target.value)} style={{ minWidth: 280 }}>
                    <option value="">Select workspace</option>
                    {workspaces.map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>
                        {workspace.name} ({workspace.root_path})
                      </option>
                    ))}
                  </select>
                  <button className="secondary-button" onClick={() => void onListFiles()} disabled={!selectedWorkspaceId}>List Files</button>
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
                          <td><span className="inline-code">{workspace.root_path}</span></td>
                          <td>{workspace.branch || "-"}</td>
                          <td>{workspace.runtime_mode}</td>
                          <td><Link href={`/tasks?workspace=${workspace.id}`}>Open tasks</Link></td>
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
                          {(scan.important_files || []).slice(0, 12).map((item) => <li key={item}>{item}</li>)}
                        </ul>
                      )}
                    </div>
                    <div className="callout">
                      <strong>Docs</strong>
                      {(scan.docs || []).length === 0 ? (
                        <div className="helper-text">No docs detected.</div>
                      ) : (
                        <ul className="list-reset">
                          {(scan.docs || []).slice(0, 12).map((item) => <li key={item}>{item}</li>)}
                        </ul>
                      )}
                    </div>
                  </div>

                  <div style={{ marginTop: 16 }} className="code-block">{JSON.stringify(scan, null, 2)}</div>
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
                  <div className="helper-text" style={{ marginBottom: 12 }}>{filesResult.count} files available for controlled access.</div>
                  <div className="code-block">{filesResult.files.slice(0, 200).join("\n")}</div>
                </>
              )}
            </Surface>
          </div>
        </div>
      </div>
    </Layout>
  );
}
