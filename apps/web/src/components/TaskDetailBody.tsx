import type {
  BatonPacket,
  ContextReference,
  ProjectEvent,
  ProviderCapability,
  RoutingDecision,
  TaskChildrenBoard,
  TaskDetail,
  TaskExecutionReport,
  TaskModelPolicy,
  AnalystDigest,
} from "../lib/types";
import { TaskCommandCenter } from "./TaskCommandCenter";
import { TaskContextPanels } from "./TaskContextPanels";
import { ExecutionOutcomePanel } from "./ExecutionOutcomePanel";
import { TaskActivityPanels } from "./TaskActivityPanels";
import { ModelStrategyPanel } from "./ModelStrategyPanel";
import { Surface } from "./Surface";

type TaskDetailBodyProps = {
  detail: TaskDetail;
  digest: AnalystDigest | null;
  events: ProjectEvent[];
  batons: BatonPacket[];
  routing: RoutingDecision | null;
  childrenBoard: TaskChildrenBoard | null;
  executionReport: TaskExecutionReport | null;
  modelPolicy: TaskModelPolicy | null;
  providerCapabilities: ProviderCapability[];
  savingPolicy: boolean;
  runningAction: string | null;
  actionMessage: string | null;
  commandPrompt: string;
  selectedReference: ContextReference | null;
  loadingReferenceId: string | null;
  onCommandPromptChange: (value: string) => void;
  onExecuteTask: () => void | Promise<void>;
  onStartRun: () => void | Promise<void>;
  onRouteTask: () => void | Promise<void>;
  onGenerateDigest: () => void | Promise<void>;
  onRefresh: () => void | Promise<void>;
  onOpenReference: (refId: string) => void | Promise<void>;
  onCopyValue: (value: string) => void | Promise<void>;
  onCloseReference: () => void;
  onSaveModelPolicy: (formData: FormData) => void | Promise<void>;
  eli5Text: (value: AnalystDigest) => string;
  formatEli5ForDisplay: (text: string) => string;
  providerSummary: (provider: string) => string | null;
};

export function TaskDetailBody({
  detail,
  digest,
  events,
  batons,
  routing,
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
  onCommandPromptChange,
  onExecuteTask,
  onStartRun,
  onRouteTask,
  onGenerateDigest,
  onRefresh,
  onOpenReference,
  onCopyValue,
  onCloseReference,
  onSaveModelPolicy,
  eli5Text,
  formatEli5ForDisplay,
  providerSummary,
}: TaskDetailBodyProps) {
  return (
    <>
      <div className="content-grid two-column">
        <div className="stack">
          <Surface
            title="Command Center"
            description="Run the current task, route it, refresh the digest, and inspect the outcome from one operator surface."
            tone="highlight"
          >
            <TaskCommandCenter
              commandPrompt={commandPrompt}
              onCommandPromptChange={onCommandPromptChange}
              onExecuteTask={onExecuteTask}
              onStartRun={onStartRun}
              onRouteTask={onRouteTask}
              onGenerateDigest={onGenerateDigest}
              onRefresh={onRefresh}
              runningAction={runningAction}
              actionMessage={actionMessage}
              disabled={false}
            />
          </Surface>

          <TaskContextPanels detail={detail} />

          <TaskActivityPanels
            digest={digest}
            events={events}
            batons={batons}
            routing={routing}
            childrenBoard={childrenBoard}
            eli5Text={eli5Text}
            formatEli5ForDisplay={formatEli5ForDisplay}
          />
        </div>
      </div>

      <Surface
        title="Execution Outcome"
        description="Everything an operator needs in one place: why the task succeeded or failed, what changed, what commands ran, and what the models actually produced."
        tone="highlight"
      >
        <ExecutionOutcomePanel
          executionReport={executionReport}
          selectedReference={selectedReference}
          loadingReferenceId={loadingReferenceId}
          onOpenReference={onOpenReference}
          onCopyValue={onCopyValue}
          onCloseReference={onCloseReference}
        />
      </Surface>

      <Surface title="Model Strategy" description="Per-stage provider and model policy used by autonomy arbitration.">
        <ModelStrategyPanel
          modelPolicy={modelPolicy}
          providerCapabilities={providerCapabilities}
          savingPolicy={savingPolicy}
          onSaveModelPolicy={onSaveModelPolicy}
          providerSummary={providerSummary}
        />
      </Surface>
    </>
  );
}
