import { useState, useRef, type ReactNode } from "react";

type Placement = "top" | "bottom" | "left" | "right";

interface TooltipProps {
  content: string;
  placement?: Placement;
  children: ReactNode;
}

const placementStyles: Record<Placement, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

export default function Tooltip({
  content,
  placement = "top",
  children,
}: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  function show() {
    timerRef.current = setTimeout(() => setVisible(true), 300);
  }

  function hide() {
    clearTimeout(timerRef.current);
    setVisible(false);
  }

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {visible && (
        <div
          role="tooltip"
          className={[
            "absolute z-50 px-[var(--space-2)] py-[var(--space-1)]",
            "bg-[var(--color-neutral-900)] text-white text-[var(--text-caption-size)]",
            "rounded-[var(--radius-md)] shadow-[var(--shadow-md)]",
            "whitespace-nowrap pointer-events-none",
            "animate-[fadeIn_var(--duration-fast)_ease-out]",
            placementStyles[placement],
          ].join(" ")}
        >
          {content}
        </div>
      )}
    </div>
  );
}
