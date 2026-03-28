import { type InputHTMLAttributes, useId } from "react";

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label: string;
  error?: string;
}

export default function Input({
  label,
  error,
  required,
  disabled,
  className = "",
  id: externalId,
  ...props
}: InputProps) {
  const autoId = useId();
  const inputId = externalId ?? autoId;
  const errorId = error ? `${inputId}-error` : undefined;

  return (
    <div className={["flex flex-col gap-[var(--space-1)]", className].join(" ")}>
      <label
        htmlFor={inputId}
        className="text-[var(--text-small-size)] leading-[var(--text-small-height)] font-medium text-[var(--color-neutral-700)]"
      >
        {label}
        {required && (
          <span className="text-[var(--color-error)] ml-0.5" aria-hidden="true">
            *
          </span>
        )}
      </label>

      <input
        id={inputId}
        required={required}
        disabled={disabled}
        aria-invalid={!!error}
        aria-describedby={errorId}
        className={[
          "h-10 px-3 rounded-[var(--radius-md)]",
          "text-[var(--text-body-size)] leading-[var(--text-body-height)]",
          "text-[var(--color-neutral-900)] placeholder:text-[var(--color-neutral-400)]",
          "outline-none border-2 transition-colors",
          "duration-[var(--duration-normal)] ease-[var(--easing-default)]",
          disabled && "opacity-50 cursor-not-allowed bg-[var(--color-neutral-100)]",
          error
            ? "border-[var(--color-error)] bg-[var(--color-error-surface)] focus:border-[var(--color-error)]"
            : "border-[var(--color-neutral-200)] bg-white focus:border-[var(--color-primary-light)]",
        ]
          .filter(Boolean)
          .join(" ")}
        {...props}
      />

      {error && (
        <p
          id={errorId}
          role="alert"
          className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-error)]"
        >
          {error}
        </p>
      )}
    </div>
  );
}
