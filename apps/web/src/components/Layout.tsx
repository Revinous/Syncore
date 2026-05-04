import Link from "next/link";
import { useRouter } from "next/router";
import { ReactNode } from "react";

const navItems = [
  {
    href: "/",
    label: "Dashboard",
    caption: "Runtime health, savings, and current delivery posture.",
  },
  {
    href: "/workspaces",
    label: "Workspaces",
    caption: "Attached repos, scans, contracts, and safe file boundaries.",
  },
  {
    href: "/tasks",
    label: "Tasks",
    caption: "Execution queue, planning targets, and active delivery work.",
  },
  {
    href: "/analyst",
    label: "Analyst Digest",
    caption: "Human-readable summaries and delivery signal interpretation.",
  },
  {
    href: "/runs",
    label: "Agent Runs",
    caption: "Planner, implementer, and reviewer execution visibility.",
  },
  {
    href: "/notifications",
    label: "Notifications",
    caption: "Research findings, alerts, and actionable inbox items.",
  },
  {
    href: "/diagnostics",
    label: "Diagnostics",
    caption: "Route registry, config, and service-level operational state.",
  },
];

export function Layout({ title, children }: { title: string; children: ReactNode }) {
  const router = useRouter();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-kicker">Local Autonomy Control Plane</div>
          <div className="brand-title">Syncore</div>
          <p className="brand-copy">
            Orchestrate repo-aware planning, execution, review, and diagnostics from one surface.
          </p>
        </div>

        <nav className="nav-group" aria-label="Primary navigation">
          {navItems.map((item) => {
            const active =
              item.href === "/"
                ? router.pathname === "/"
                : router.pathname === item.href || router.pathname.startsWith(`${item.href}/`);
            return (
              <Link key={item.href} href={item.href} className={`nav-link${active ? " active" : ""}`}>
                <span className="nav-label">{item.label}</span>
                <span className="nav-caption">{item.caption}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-footnote">
          <strong>{title}</strong>
          <div>Built for local-first engineering operations, not toy dashboards.</div>
        </div>
      </aside>

      <main className="main-shell">{children}</main>
    </div>
  );
}
