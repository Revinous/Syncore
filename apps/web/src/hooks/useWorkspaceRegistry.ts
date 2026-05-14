import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  createWorkspace,
  listWorkspaceFiles,
  listWorkspaces,
  scanWorkspace,
} from "../lib/api";
import type { Workspace, WorkspaceFile, WorkspaceScanResult } from "../lib/types";

export function useWorkspaceRegistry() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>("");
  const [scanResult, setScanResult] = useState<WorkspaceScanResult | null>(null);
  const [filesResult, setFilesResult] = useState<WorkspaceFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);

  const [name, setName] = useState("syncore");
  const [rootPath, setRootPath] = useState("./");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");

  const selected = useMemo(
    () => workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ?? null,
    [workspaces, selectedWorkspaceId],
  );

  async function load(background = false) {
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const nextWorkspaces = await listWorkspaces();
      setWorkspaces(nextWorkspaces);
      if (!selectedWorkspaceId && nextWorkspaces.length > 0) {
        setSelectedWorkspaceId(nextWorkspaces[0].id);
      }
      setLastLoadedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workspaces");
    } finally {
      if (background) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load(true);
    }, 20000);
    return () => window.clearInterval(timer);
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
  const secondsSinceRefresh = lastLoadedAt
    ? Math.max(0, Math.round((Date.now() - lastLoadedAt.getTime()) / 1000))
    : null;
  const freshnessState =
    secondsSinceRefresh === null ? "unknown" : secondsSinceRefresh <= 25 ? "fresh" : "stale";
  const isOfflineError = error?.includes("Could not reach Syncore API");

  return {
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
    load,
    onCreateWorkspace,
    onScan,
    onListFiles,
  };
}
