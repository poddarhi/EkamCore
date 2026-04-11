import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

type ModalSize = "sm" | "md" | "lg";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  size?: ModalSize;
  preventClose?: boolean;
  children: ReactNode;
}

const sizeStyles: Record<ModalSize, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
};

export default function Modal({
  open,
  onClose,
  title,
  size = "md",
  preventClose = false,
  children,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !preventClose) onClose();
    },
    [onClose, preventClose],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";
      dialogRef.current?.focus();
      return () => {
        document.removeEventListener("keydown", handleEscape);
        document.body.style.overflow = "";
      };
    }
  }, [open, handleEscape]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 animate-[fadeIn_var(--duration-normal)_ease-out]"
        onClick={preventClose ? undefined : onClose}
        aria-hidden="true"
      />
      {/* Content */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={[
          "relative z-10 w-full bg-[var(--color-white)] rounded-[var(--radius-xl)] shadow-[var(--shadow-xl)]",
          "animate-[slideUp_var(--duration-normal)_var(--easing-default)]",
          "outline-none",
          sizeStyles[size],
        ].join(" ")}
      >
        {title && (
          <div className="flex items-center justify-between px-[var(--space-6)] py-[var(--space-4)] border-b border-[var(--color-neutral-200)]">
            <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)]">
              {title}
            </h2>
            {!preventClose && (
              <button
                onClick={onClose}
                className="p-1.5 rounded-[var(--radius-md)] text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-700)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
                aria-label="Close dialog"
              >
                <X size={18} aria-hidden="true" />
              </button>
            )}
          </div>
        )}
        <div className="px-[var(--space-6)] py-[var(--space-4)]">{children}</div>
      </div>
    </div>
  );
}
