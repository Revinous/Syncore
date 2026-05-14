import type { ProviderCapability, TaskModelPolicy } from "../lib/types";
import { EmptyState } from "./EmptyState";

type ModelStrategyPanelProps = {
  modelPolicy: TaskModelPolicy | null;
  providerCapabilities: ProviderCapability[];
  savingPolicy: boolean;
  onSaveModelPolicy: (formData: FormData) => void | Promise<void>;
  providerSummary: (provider: string) => string | null;
};

export function ModelStrategyPanel({
  modelPolicy,
  providerCapabilities,
  savingPolicy,
  onSaveModelPolicy,
  providerSummary,
}: ModelStrategyPanelProps) {
  if (!modelPolicy) {
    return (
      <EmptyState
        message="No model strategy is loaded for this task."
        hint="Model strategy appears once the orchestrator or operator assigns provider and model preferences."
      />
    );
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void onSaveModelPolicy(new FormData(event.currentTarget));
      }}
      className="stack"
    >
      <div className="helper-text">
        Default provider and model are the baseline. Stage fields can override plan, execute, and review independently. Arbitration then applies your cost, speed, context, and continuity rules.
      </div>
      <div className="form-grid two-up">
        <label className="field-label">
          Default provider
          <input className="field" name="default_provider" defaultValue={modelPolicy.default_provider} />
        </label>
        <label className="field-label">
          Default model
          <input className="field" name="default_model" defaultValue={modelPolicy.default_model} />
        </label>
        <label className="field-label">
          Plan provider
          <input className="field" name="plan_provider" defaultValue={modelPolicy.plan.provider ?? ""} />
        </label>
        <label className="field-label">
          Plan model
          <input className="field" name="plan_model" defaultValue={modelPolicy.plan.model ?? ""} />
        </label>
        <label className="field-label">
          Execute provider
          <input className="field" name="execute_provider" defaultValue={modelPolicy.execute.provider ?? ""} />
        </label>
        <label className="field-label">
          Execute model
          <input className="field" name="execute_model" defaultValue={modelPolicy.execute.model ?? ""} />
        </label>
        <label className="field-label">
          Review provider
          <input className="field" name="review_provider" defaultValue={modelPolicy.review.provider ?? ""} />
        </label>
        <label className="field-label">
          Review model
          <input className="field" name="review_model" defaultValue={modelPolicy.review.model ?? ""} />
        </label>
        <label className="field-label">
          Optimization goal
          <select className="field" name="optimization_goal" defaultValue={modelPolicy.optimization_goal}>
            <option value="balanced">balanced</option>
            <option value="quality">quality</option>
            <option value="speed">speed</option>
            <option value="cost">cost</option>
            <option value="context">context</option>
          </select>
        </label>
        <label className="field-label">
          Minimum context window
          <input className="field" name="minimum_context_window" type="number" min={0} defaultValue={modelPolicy.minimum_context_window} />
        </label>
        <label className="field-label">
          Max latency tier
          <select className="field" name="max_latency_tier" defaultValue={modelPolicy.max_latency_tier ?? ""}>
            <option value="">any</option>
            <option value="fast">fast</option>
            <option value="medium">medium</option>
            <option value="slow">slow</option>
          </select>
        </label>
        <label className="field-label">
          Max cost tier
          <select className="field" name="max_cost_tier" defaultValue={modelPolicy.max_cost_tier ?? ""}>
            <option value="">any</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
        <label className="field-label" style={{ gridColumn: "1 / -1" }}>
          Fallback order
          <input className="field" name="fallback_order" defaultValue={modelPolicy.fallback_order.join(", ")} />
        </label>
      </div>
      <div className="checkbox-row">
        <label className="checkbox-label"><input name="allow_cross_provider_switching" type="checkbox" defaultChecked={modelPolicy.allow_cross_provider_switching} /> allow cross-provider switching</label>
        <label className="checkbox-label"><input name="maintain_context_continuity" type="checkbox" defaultChecked={modelPolicy.maintain_context_continuity} /> maintain context continuity</label>
        <label className="checkbox-label"><input name="prefer_reviewer_provider" type="checkbox" defaultChecked={modelPolicy.prefer_reviewer_provider} /> prefer reviewer provider</label>
      </div>
      <div className="control-row">
        <button className="button" type="submit" disabled={savingPolicy}>{savingPolicy ? "Saving..." : "Save strategy"}</button>
      </div>
      {providerCapabilities.length > 0 ? (
        <div className="panel-grid two-up">
          {providerCapabilities.map((item) => (
            <div className="meta-card" key={item.provider}>
              <span className="meta-label">{item.provider}</span>
              <div className="meta-value">{providerSummary(item.provider)}; strengths {item.strengths.join(", ")}</div>
            </div>
          ))}
        </div>
      ) : null}
    </form>
  );
}
