import { StatusBadge } from "./StatusBadge";

type TaskStatusStripProps = {
  freshnessState: string;
  executionState: string;
  verificationStatus: string | null | undefined;
  lastLoadedAt: Date | null;
  refreshing: boolean;
};

export function TaskStatusStrip({
  freshnessState,
  executionState,
  verificationStatus,
  lastLoadedAt,
  refreshing,
}: TaskStatusStripProps) {
  return (
    <div className="operator-strip">
      <div className="operator-strip-block">
        <span className="operator-strip-label">Freshness</span>
        <div className="operator-strip-value"><StatusBadge status={freshnessState} /></div>
      </div>
      <div className="operator-strip-block">
        <span className="operator-strip-label">Execution</span>
        <div className="operator-strip-value"><StatusBadge status={executionState} /></div>
      </div>
      <div className="operator-strip-block">
        <span className="operator-strip-label">Verification</span>
        <div className="operator-strip-value">
          {verificationStatus ? <StatusBadge status={verificationStatus} /> : "pending"}
        </div>
      </div>
      <div className="operator-strip-block">
        <span className="operator-strip-label">Last Refresh</span>
        <div className="operator-strip-value">
          {lastLoadedAt ? `${lastLoadedAt.toLocaleTimeString()}${refreshing ? " · refreshing" : ""}` : "waiting"}
        </div>
      </div>
      <div className="operator-strip-block">
        <span className="operator-strip-label">Cadence</span>
        <div className="operator-strip-value">auto every 10s</div>
      </div>
    </div>
  );
}
