"use client";

export function PhaseBanner({ label }: { label: string }) {
  return (
    <p className="phase" role="status" aria-live="polite">
      <span className="pip" aria-hidden />
      {label}
    </p>
  );
}

export function ErrorNotice({
  message,
  canRetry,
  busy,
  onRetry,
}: {
  message: string;
  canRetry: boolean;
  busy: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="notice" role="alert">
      <pre>{message}</pre>
      {canRetry && (
        <div className="actions">
          <button type="button" className="ghost" onClick={onRetry} disabled={busy}>
            Try that turn again
          </button>
          <span className="muted">Your progress is saved either way.</span>
        </div>
      )}
    </div>
  );
}

export function Track({ done, total }: { done: number; total: number }) {
  return (
    <div className="track" aria-hidden>
      {Array.from({ length: total }, (_, index) => (
        <span
          key={index}
          data-state={index < done ? "done" : index === done ? "current" : "todo"}
        />
      ))}
    </div>
  );
}
