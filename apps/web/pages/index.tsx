import { useEffect, useState } from "react";

import { apiBaseUrl } from "../lib/config";

type HealthResponse = {
  status: string;
  service: string;
  environment: string;
};

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/health`);
        if (!response.ok) {
          throw new Error(`Health check failed with status ${response.status}`);
        }
        const payload = (await response.json()) as HealthResponse;
        setHealth(payload);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Unknown error");
      }
    }

    loadHealth();
  }, []);

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif" }}>
      <h1>Agent Workforce OS</h1>
      <p>Local shell is running.</p>
      <p>API Base URL: {apiBaseUrl}</p>
      {health && <p>Orchestrator status: {health.status}</p>}
      {error && <p>Health check error: {error}</p>}
    </main>
  );
}
