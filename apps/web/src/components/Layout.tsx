import Link from "next/link";
import { ReactNode } from "react";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/workspaces", label: "Workspaces" },
  { href: "/tasks", label: "Tasks" },
  { href: "/runs", label: "Agent Runs" },
  { href: "/diagnostics", label: "Diagnostics" },
];

export function Layout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ fontFamily: "Arial, sans-serif", minHeight: "100vh", background: "#f7f8fa" }}>
      <header style={{ borderBottom: "1px solid #d8dbe2", background: "#fff", padding: "12px 20px" }}>
        <strong>Syncore Control Panel</strong>
      </header>
      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", minHeight: "calc(100vh - 50px)" }}>
        <nav style={{ borderRight: "1px solid #d8dbe2", background: "#fff", padding: 16 }}>
          {navItems.map((item) => (
            <div key={item.href} style={{ marginBottom: 8 }}>
              <Link href={item.href}>{item.label}</Link>
            </div>
          ))}
        </nav>
        <main style={{ padding: 20 }}>
          <h1 style={{ marginTop: 0 }}>{title}</h1>
          {children}
        </main>
      </div>
    </div>
  );
}
