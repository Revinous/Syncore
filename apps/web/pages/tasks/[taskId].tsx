import { useRouter } from "next/router";

import { TaskDetailBody } from "../../src/components/TaskDetailBody";
import { TaskStatusStrip } from "../../src/components/TaskStatusStrip";
import { ErrorState } from "../../src/components/ErrorState";
import { Layout } from "../../src/components/Layout";
import { LoadingState } from "../../src/components/LoadingState";
import { PageHeader } from "../../src/components/PageHeader";
import { StatusBadge } from "../../src/components/StatusBadge";
import { useTaskDetailData } from "../../src/hooks/useTaskDetailData";
import {
  buildDigestEli5,
  deriveTaskExecutionState,
  deriveTaskFreshness,
  formatDigestEli5,
  isOfflineTaskError,
  summarizeProviderCapability,
} from "../../src/lib/taskDetailPresentation";

export default function TaskDetailPage() {
  const router = useRouter();
  const taskId = typeof router.query.taskId === "string" ? router.query.taskId : "";
  const {
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
  } = useTaskDetailData(taskId);

  const { freshnessState } = deriveTaskFreshness(lastLoadedAt);
  const executionState = deriveTaskExecutionState(detail, executionReport);
  const isOfflineError = isOfflineTaskError(error);

  return (
    <Layout title="Task Detail">
      <div className="page-shell">
        <PageHeader
          title={detail?.task.title ?? "Task Detail"}
          subtitle="Inspect a single task across task metadata, child execution, baton handoffs, routing, and the model strategy shaping autonomy behavior."
          kicker="Task Control"
          metrics={[
            { label: "Task Status", value: detail ? <StatusBadge status={detail.task.status} /> : "loading" },
            { label: "Task Type", value: detail?.task.task_type ?? "n/a" },
            { label: "Complexity", value: detail?.task.complexity ?? "n/a" },
          ]}
        />

        <TaskStatusStrip
          freshnessState={freshnessState}
          executionState={executionState}
          verificationStatus={executionReport?.verification_status}
          lastLoadedAt={lastLoadedAt}
          refreshing={refreshing}
        />

        {loading && <LoadingState message="Loading task detail..." />}
        {error && (
          <ErrorState
            title={isOfflineError ? "Syncore API offline" : "Operator attention required"}
            message={error}
            hint={
              isOfflineError
                ? "The browser cannot reach the local orchestrator. Start Syncore services, then refresh this task."
                : "Refresh the surface. If this persists, check diagnostics and service health."
            }
          />
        )}

        {detail ? (
          <TaskDetailBody
            detail={detail}
            digest={digest}
            events={events}
            batons={batons}
            routing={routing}
            childrenBoard={childrenBoard}
            executionReport={executionReport}
            modelPolicy={modelPolicy}
            providerCapabilities={providerCapabilities}
            savingPolicy={savingPolicy}
            runningAction={runningAction}
            actionMessage={actionMessage}
            commandPrompt={commandPrompt}
            selectedReference={selectedReference}
            loadingReferenceId={loadingReferenceId}
            onCommandPromptChange={setCommandPrompt}
            onExecuteTask={executeTask}
            onStartRun={startRun}
            onRouteTask={routeTask}
            onGenerateDigest={generateTaskDigest}
            onRefresh={load}
            onOpenReference={openReference}
            onCopyValue={copyValue}
            onCloseReference={() => setSelectedReference(null)}
            onSaveModelPolicy={saveModelPolicy}
            eli5Text={buildDigestEli5}
            formatEli5ForDisplay={formatDigestEli5}
            providerSummary={(provider) => summarizeProviderCapability(providerCapabilities, provider)}
          />
        ) : null}
      </div>
    </Layout>
  );
}
