import { ReactNode } from "react";

export function Surface({
  title,
  description,
  actions,
  children,
  tone,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  tone?: "default" | "inset" | "highlight";
}) {
  const toneClass = tone ? ` ${tone}` : "";
  return (
    <section className={`surface${toneClass}`}>
      {title || actions || description ? (
        <div className="section-header">
          <div>
            {title ? <h2 className="section-title">{title}</h2> : null}
            {description ? <p className="section-copy">{description}</p> : null}
          </div>
          {actions ? <div className="control-row">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
