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

  return (
    <Layout title="Workspaces">
      {loading && <LoadingState message="Loading workspaces..." />}
      {error && <ErrorState message={error} />}

      <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
        <h2>Add Workspace</h2>
        <form onSubmit={onCreateWorkspace} style={{ display: "grid", gap: 8, maxWidth: 640 }}>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" required />
          <input value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="Root path" required />
          <input value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} placeholder="Repo URL (optional)" />
          <input value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="Branch (optional)" />
          <button type="submit">Create Workspace</button>
        </form>
      </section>

      <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
        <h2>Workspace List</h2>
        {workspaces.length === 0 ? (
          <EmptyState message="No workspaces registered yet." />
        ) : (
          <>
            <select
              value={selectedWorkspaceId}
              onChange={(event) => setSelectedWorkspaceId(event.target.value)}
            >
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name} ({workspace.root_path})
                </option>
              ))}
            </select>{" "}
            <button onClick={() => void onScan()}>Scan</button>{" "}
            <button onClick={() => void onListFiles()}>List Files</button>

            <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th align="left">Name</th>
                  <th align="left">Root Path</th>
                  <th align="left">Branch</th>
                  <th align="left">Mode</th>
                </tr>
              </thead>
              <tbody>
                {workspaces.map((workspace) => (
                  <tr key={workspace.id}>
                    <td>{workspace.name}</td>
                    <td>{workspace.root_path}</td>
                    <td>{workspace.branch || "-"}</td>
                    <td>{workspace.runtime_mode}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {selected && scanResult && (
        <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
          <h2>Scan: {selected.name}</h2>
          <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(scanResult.scan, null, 2)}</pre>
        </section>
      )}

      {selected && filesResult && (
        <section style={{ marginBottom: 16, background: "#fff", border: "1px solid #d8dbe2", borderRadius: 8, padding: 12 }}>
          <h2>Files: {selected.name} ({filesResult.count})</h2>
          {filesResult.files.length === 0 ? (
            <EmptyState message="No safe files exposed." />
          ) : (
            <ul>
              {filesResult.files.slice(0, 200).map((path) => (
                <li key={path}>{path}</li>
              ))}
            </ul>
          )}
        </section>
      )}
    </Layout>
  );
}
