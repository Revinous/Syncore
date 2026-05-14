import { Layout } from "../src/components/Layout";
import { WorkspaceRegistryBody } from "../src/components/WorkspaceRegistryBody";
import { useWorkspaceRegistry } from "../src/hooks/useWorkspaceRegistry";

export default function WorkspacesPage() {
  const workspaceRegistry = useWorkspaceRegistry();

  return (
    <Layout title="Workspaces">
      <WorkspaceRegistryBody {...workspaceRegistry} onLoad={() => void workspaceRegistry.load()} />
    </Layout>
  );
}
