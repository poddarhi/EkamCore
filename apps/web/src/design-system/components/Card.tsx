import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export default function Card({
  children,
  onClick,
  className = "",
  ...props
}: CardProps) {
  const interactive = !!onClick;

  return (
    <div
      className={[
        "bg-[var(--color-white)] border border-[var(--color-neutral-200)]",
        "rounded-[var(--radius-lg)] shadow-[var(--shadow-sm)]",
        "p-[var(--space-4)]",
        "transition-all duration-[var(--duration-normal)] ease-[var(--easing-default)]",
        interactive &&
          "cursor-pointer hover:border-[var(--color-neutral-400)] hover:shadow-[var(--shadow-md)]",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={onClick}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.(e as unknown as React.MouseEvent<HTMLDivElement>);
              }
            }
          : undefined
      }
      {...props}
    >
      {children}
    </div>
  );
}
