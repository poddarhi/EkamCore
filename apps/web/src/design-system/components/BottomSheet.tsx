import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  snapPoints?: number[];
  children: ReactNode;
}

export default function BottomSheet({
  open,
  onClose,
  snapPoints = [0.5, 1.0],
  children,
}: BottomSheetProps) {
  const [snapIdx, setSnapIdx] = useState(0);
  const sheetRef = useRef<HTMLDivElement>(null);
  const startY = useRef(0);

  const height = `${snapPoints[snapIdx] * 100}vh`;

  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      setSnapIdx(0);
      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";
      return () => {
        document.removeEventListener("keydown", handleEscape);
        document.body.style.overflow = "";
      };
    }
  }, [open, handleEscape]);

  function handlePointerDown(e: React.PointerEvent) {
    startY.current = e.clientY;
  }

  function handlePointerUp(e: React.PointerEvent) {
    const delta = e.clientY - startY.current;
    if (delta > 80) {
      if (snapIdx === 0) onClose();
      else setSnapIdx((i) => Math.max(0, i - 1));
    } else if (delta < -80 && snapIdx < snapPoints.length - 1) {
      setSnapIdx((i) => i + 1);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden="true" />
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        className="absolute bottom-0 left-0 right-0 bg-[var(--color-white)] rounded-t-[var(--radius-xl)] shadow-[var(--shadow-xl)] transition-all duration-[var(--duration-slow)] ease-[var(--easing-default)] overflow-y-auto"
        style={{ height }}
      >
        {/* Drag handle */}
        <div
          className="flex justify-center py-[var(--space-2)] cursor-grab"
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
          role="separator"
          aria-label="Drag to resize"
        >
          <div className="w-10 h-1 rounded-full bg-[var(--color-neutral-300)]" />
        </div>
        <div className="px-[var(--space-4)] pb-[var(--space-4)]">{children}</div>
      </div>
    </div>
  );
}
