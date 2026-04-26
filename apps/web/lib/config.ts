export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export const serverApiBaseUrl =
  process.env.ORCHESTRATOR_INTERNAL_URL?.replace(/\/$/, "") || apiBaseUrl;
