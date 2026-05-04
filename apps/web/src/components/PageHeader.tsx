import { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  kicker = "Control Surface",
  actions,
  metrics,
}: {
  title: string;
  subtitle: string;
  kicker?: string;
  actions?: ReactNode;
  metrics?: Array<{ label: string; value: ReactNode }>;
}) {
  return (
    <header className="page-hero">
      <div className="page-header-copy">
        <div className="kicker">{kicker}</div>
        <h1 className="page-title">{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      <div className="stack" style={{ alignItems: "stretch" }}>
        {actions ? <div className="page-actions">{actions}</div> : null}
        {metrics?.length ? (
          <div className="hero-metrics">
            {metrics.map((metric) => (
              <div className="hero-metric" key={metric.label}>
                <div className="hero-metric-label">{metric.label}</div>
                <div className="hero-metric-value">{metric.value}</div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </header>
  );
}
