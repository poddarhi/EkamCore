/**
 * SnoozePicker — inline date option selector for follow-up snooze (S14-009).
 */

import { useState } from "react";

interface SnoozePickerProps {
  onPick: (isoDate: string) => void;
  onCancel: () => void;
}

function addDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().split("T")[0];
}

export default function SnoozePicker({ onPick, onCancel }: SnoozePickerProps) {
  const [custom, setCustom] = useState("");
  return (
    <div className="mt-2 flex flex-wrap gap-2 items-center text-xs">
      <button type="button" onClick={() => onPick(addDays(1))} className="px-2 py-1 rounded border border-[var(--color-neutral-200)] hover:bg-[var(--color-neutral-50)]">
        Tomorrow
      </button>
      <button type="button" onClick={() => onPick(addDays(3))} className="px-2 py-1 rounded border border-[var(--color-neutral-200)] hover:bg-[var(--color-neutral-50)]">
        In 3 days
      </button>
      <button type="button" onClick={() => onPick(addDays(7))} className="px-2 py-1 rounded border border-[var(--color-neutral-200)] hover:bg-[var(--color-neutral-50)]">
        Next week
      </button>
      <input
        type="date"
        value={custom}
        min={addDays(1)}
        onChange={(e) => setCustom(e.target.value)}
        className="px-2 py-1 rounded border border-[var(--color-neutral-200)] text-xs"
        aria-label="Custom snooze date"
      />
      {custom && (
        <button type="button" onClick={() => onPick(custom)} className="text-[var(--color-primary)] hover:underline">
          Snooze
        </button>
      )}
      <button type="button" onClick={onCancel} className="text-[var(--color-neutral-500)] hover:underline">
        Cancel
      </button>
    </div>
  );
}
