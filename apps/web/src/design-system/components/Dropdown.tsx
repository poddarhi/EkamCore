import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

interface DropdownOption {
  value: string;
  label: string;
}

interface DropdownProps {
  options: DropdownOption[];
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export default function Dropdown({
  options,
  value,
  onChange,
  placeholder = "Select...",
  disabled = false,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const showSearch = options.length > 10;
  const filtered = search
    ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase()))
    : options;

  const selectedLabel = options.find((o) => o.value === value)?.label;

  const close = useCallback(() => {
    setOpen(false);
    setSearch("");
    setHighlightIdx(-1);
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) close();
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [close]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") { close(); return; }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) { setOpen(true); return; }
      setHighlightIdx((i) => Math.min(i + 1, filtered.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    }
    if (e.key === "Enter" && open && highlightIdx >= 0) {
      e.preventDefault();
      onChange(filtered[highlightIdx].value);
      close();
    }
  }

  return (
    <div ref={containerRef} className="relative" onKeyDown={handleKeyDown}>
      <button
        type="button"
        onClick={() => !disabled && setOpen((v) => !v)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={[
          "flex items-center justify-between w-full h-10 px-3 rounded-[var(--radius-md)]",
          "border border-[var(--color-neutral-200)] bg-[var(--color-white)]",
          "text-[var(--text-body-size)] text-left",
          "transition-colors duration-[var(--duration-normal)]",
          "outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]",
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-[var(--color-neutral-400)]",
        ].join(" ")}
      >
        <span className={selectedLabel ? "text-[var(--color-neutral-900)]" : "text-[var(--color-neutral-400)]"}>
          {selectedLabel ?? placeholder}
        </span>
        <ChevronDown size={16} className="text-[var(--color-neutral-400)] shrink-0" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto bg-[var(--color-white)] border border-[var(--color-neutral-200)] rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]"
        >
          {showSearch && (
            <div className="p-2 border-b border-[var(--color-neutral-100)]">
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setHighlightIdx(0); }}
                placeholder="Filter..."
                className="w-full h-8 px-2 text-[var(--text-small-size)] border border-[var(--color-neutral-200)] rounded-[var(--radius-sm)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
                autoFocus
              />
            </div>
          )}
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-[var(--text-small-size)] text-[var(--color-neutral-400)]">No options</div>
          ) : (
            filtered.map((opt, i) => (
              <div
                key={opt.value}
                role="option"
                aria-selected={opt.value === value}
                onClick={() => { onChange(opt.value); close(); }}
                className={[
                  "px-3 py-2 text-[var(--text-body-size)] cursor-pointer transition-colors",
                  opt.value === value ? "bg-[var(--color-primary-surface)] text-[var(--color-primary)] font-medium" : "text-[var(--color-neutral-900)]",
                  i === highlightIdx ? "bg-[var(--color-neutral-100)]" : "",
                  "hover:bg-[var(--color-neutral-100)]",
                ].join(" ")}
              >
                {opt.label}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
