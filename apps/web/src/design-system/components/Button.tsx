import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] focus-visible:shadow-[var(--shadow-focus)]",
  secondary:
    "bg-transparent text-[var(--color-primary)] border border-[var(--color-primary)] hover:bg-[var(--color-primary-surface)] focus-visible:shadow-[var(--shadow-focus)]",
  ghost:
    "bg-transparent text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] focus-visible:shadow-[var(--shadow-focus)]",
  danger:
    "bg-[var(--color-error)] text-white hover:bg-[#c82333] focus-visible:shadow-[var(--shadow-focus)]",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[var(--text-small-size)]",
  md: "h-10 px-4 text-[var(--text-body-size)]",
  lg: "h-12 px-6 text-[var(--text-body-size)]",
};

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  icon,
  children,
  className = "",
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      className={[
        "inline-flex items-center justify-center gap-2 font-medium",
        "rounded-[var(--radius-md)] outline-none",
        "transition-colors",
        `duration-[var(--duration-normal)] ease-[var(--easing-default)]`,
        variantStyles[variant],
        sizeStyles[size],
        isDisabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      disabled={isDisabled}
      aria-disabled={isDisabled}
      {...props}
    >
      {loading ? (
        <svg
          className="h-4 w-4 animate-spin"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      ) : (
        <>
          {icon && <span className="shrink-0">{icon}</span>}
          {children}
        </>
      )}
    </button>
  );
}
