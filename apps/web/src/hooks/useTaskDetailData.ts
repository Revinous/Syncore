import { useEffect, useState } from "react";

import {
  createAgentRun,
  executeTaskAuto,
  generateDigest,
  getContextReference,
  getTask,
  getTaskChildren,
  getTaskDigest,
  getTaskExecutionReport,
  getTaskModelPolicy,
  getTaskRouting,
  listProviderCapabilities,
  listTaskBatonPackets,
  listTaskEvents,
  routeNextAction,
  updateTaskModelPolicy,
} from "../lib/api";
import type {
  AnalystDigest,
  BatonPacket,
  ContextReference,
  ProjectEvent,
  ProviderCapability,
  RoutingDecision,
  TaskChildrenBoard,
  TaskDetail,
  TaskExecutionReport,
  TaskModelPolicy,
} from "../lib/types";

export function useTaskDetailData(taskId: string) {
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [batons, setBatons] = useState<BatonPacket[]>([]);
  const [routing, setRouting] = useState<RoutingDecision | null>(null);
  const [digest, setDigest] = useState<AnalystDigest | null>(null);
  const [childrenBoard, setChildrenBoard] = useState<TaskChildrenBoard | null>(null);
  const [executionReport, setExecutionReport] = useState<TaskExecutionReport | null>(null);
  const [modelPolicy, setModelPolicy] = useState<TaskModelPolicy | null>(null);
  const [providerCapabilities, setProviderCapabilities] = useState<ProviderCapability[]>([]);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [runningAction, setRunningAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [commandPrompt, setCommandPrompt] = useState("");
  const [selectedReference, setSelectedReference] = useState<ContextReference | null>(null);
  const [loadingReferenceId, setLoadingReferenceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(background = false) {
    if (!taskId) return;
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const [taskDetail, eventData, batonData] = await Promise.all([
        getTask(taskId),
        listTaskEvents(taskId),
        listTaskBatonPackets(taskId),
      ]);
      setDetail(taskDetail);
      setCommandPrompt((existing) =>
        existing.trim().length > 0
          ? existing
          : `Implement the task "${taskDetail.task.title}" in the workspace, verify the result, and report the final outcome.`,
      );
      setEvents(eventData);
      setBatons(batonData);
      try {
        setRouting(await getTaskRouting(taskId));
      } catch {
        setRouting(null);
      }
      try {
        setDigest(await getTaskDigest(taskId));
      } catch {
        setDigest(null);
      }
      try {
        setChildrenBoard(await getTaskChildren(taskId));
      } catch {
        setChildrenBoard(null);
      }
      try {
        setExecutionReport(await getTaskExecutionReport(taskId));
      } catch {
        setExecutionReport(null);
      }
      try {
        setModelPolicy(await getTaskModelPolicy(taskId));
      } catch {
        setModelPolicy(null);
      }
      try {
        setProviderCapabilities(await listProviderCapabilities());
      } catch {
        setProviderCapabilities([]);
      }
      setLastLoadedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load task detail");
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
    if (!taskId) return;
    const timer = window.setInterval(() => {
      void load(true);
    }, 10000);
    return () => window.clearInterval(timer);
  }, [taskId]);

  async function startRun() {
    if (!taskId) return;
    setRunningAction("start-run");
    setActionMessage(null);
    try {
      await createAgentRun({ task_id: taskId, role: "coder", status: "running" });
      setActionMessage(
        "Agent run record created. Use Execute Task to run the current task against the configured model strategy.",
      );
      await load();
    } finally {
      setRunningAction(null);
    }
  }

  async function routeTask() {
    if (!detail) return;
    setRunningAction("route");
    setActionMessage(null);
    try {
      const decision = await routeNextAction({
        task_type: detail.task.task_type,
        complexity: detail.task.complexity,
        requires_memory: events.length > 0,
      });
      setRouting(decision);
      setActionMessage(`Routing updated: ${decision.worker_role} on ${decision.model_tier}.`);
    } finally {
      setRunningAction(null);
    }
  }

  async function generateTaskDigest() {
    if (!taskId) return;
    setRunningAction("digest");
    setActionMessage(null);
    try {
      const nextDigest = await generateDigest({ task_id: taskId, limit: 50 });
      setDigest(nextDigest);
      setActionMessage("Digest generated from the current task stream.");
    } finally {
      setRunningAction(null);
    }
  }

  async function executeTask() {
    if (!taskId || !commandPrompt.trim()) return;
    setRunningAction("execute");
    setActionMessage(null);
    setError(null);
    try {
      const response = await executeTaskAuto({
        task_id: taskId,
        stage: "execute",
        prompt: commandPrompt.trim(),
        target_agent: "coder",
        target_model: modelPolicy?.execute.model || modelPolicy?.default_model || undefined,
        provider: modelPolicy?.execute.provider || modelPolicy?.default_provider || undefined,
        agent_role: "coder",
        token_budget: 8000,
      });
      setActionMessage(
        `Execution finished via ${response.provider}/${response.target_model}. Estimated tokens: ${response.total_estimated_tokens}.`,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task execution failed");
    } finally {
      setRunningAction(null);
    }
  }

  async function openReference(refId: string) {
    setLoadingReferenceId(refId);
    try {
      const reference = await getContextReference(refId);
      setSelectedReference(reference);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load artifact reference");
    } finally {
      setLoadingReferenceId(null);
    }
  }

  async function copyValue(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setActionMessage("Copied to clipboard.");
    } catch {
      setActionMessage("Clipboard access is unavailable in this browser context.");
    }
  }

  async function saveModelPolicy(formData: FormData) {
    if (!taskId) return;
    setSavingPolicy(true);
    setError(null);
    try {
      const payload = {
        default_provider: String(formData.get("default_provider") || ""),
        default_model: String(formData.get("default_model") || ""),
        plan_provider: String(formData.get("plan_provider") || ""),
        plan_model: String(formData.get("plan_model") || ""),
        execute_provider: String(formData.get("execute_provider") || ""),
        execute_model: String(formData.get("execute_model") || ""),
        review_provider: String(formData.get("review_provider") || ""),
        review_model: String(formData.get("review_model") || ""),
        fallback_order: String(formData.get("fallback_order") || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        optimization_goal: String(formData.get("optimization_goal") || "balanced"),
        allow_cross_provider_switching: formData.get("allow_cross_provider_switching") === "on",
        maintain_context_continuity: formData.get("maintain_context_continuity") === "on",
        minimum_context_window: Number(formData.get("minimum_context_window") || 0),
        max_latency_tier: String(formData.get("max_latency_tier") || "") || null,
        max_cost_tier: String(formData.get("max_cost_tier") || "") || null,
        prefer_reviewer_provider: formData.get("prefer_reviewer_provider") === "on",
      };
      const next = await updateTaskModelPolicy(taskId, payload);
      setModelPolicy(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save model strategy");
    } finally {
      setSavingPolicy(false);
    }
  }

  return {
    detail,
    events,
    batons,
    routing,
    digest,
    childrenBoard,
    executionReport,
    modelPolicy,
    providerCapabilities,
    savingPolicy,
    runningAction,
    actionMessage,
    commandPrompt,
    selectedReference,
    loadingReferenceId,
    loading,
    refreshing,
    lastLoadedAt,
    error,
    setCommandPrompt,
    setSelectedReference,
    load,
    startRun,
    routeTask,
    generateTaskDigest,
    executeTask,
    openReference,
    copyValue,
    saveModelPolicy,
  };
}
