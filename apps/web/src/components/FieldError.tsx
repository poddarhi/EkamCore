/**
 * Inline field-level error display (S10-002).
 *
 * Renders below form inputs for validation errors.
 */

import { AlertCircle } from "lucide-react";

interface FieldErrorProps {
  /** Error message to display. If falsy, nothing renders. */
  message?: string | null;
  /** HTML id of the input this error describes (for aria-describedby). */
  id?: string;
}

export default function FieldError({ message, id }: FieldErrorProps) {
  if (!message) return null;

  return (
    <p
      id={id}
      role="alert"
      className="mt-[var(--space-1)] flex items-center gap-1 text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-error)]"
    >
      <AlertCircle size={12} className="shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}
