/**
 * TopBarPersonSearch — person quick-finder that lives in the top bar (S13-009).
 *
 * Replaces the disabled placeholder input. Typing any text runs a
 * debounced ``usePeopleList`` query; typing ``@`` as the first char
 * strips it and switches the input into explicit person-search
 * mode (visual cue only for now — the query behind the scenes is
 * identical). Up to 5 matches render in a dropdown, keyboard
 * navigable with ↑ / ↓ / Enter; Escape closes.
 *
 * A full command palette (Cmd+K across all entity types) is
 * deferred — this component covers the "find a person fast" need
 * that S13-009 actually calls for.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

import PersonAvatar from "./PersonAvatar";
import { useFlag } from "../../contexts/FlagContext";
import { usePeopleList, useFaceConsent } from "../../hooks/usePeople";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export default function TopBarPersonSearch() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted } = useFaceConsent();
  const navigate = useNavigate();

  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Strip an optional leading "@" so "@alice" and "alice" behave the
  // same — the sigil is just a visual cue that the input is a
  // person finder.
  const raw = value.startsWith("@") ? value.slice(1) : value;
  const debounced = useDebounced(raw.trim(), 200);

  const shouldQuery = enabled && accepted && debounced.length > 0;
  const { data } = usePeopleList(
    { limit: 5, search: shouldQuery ? debounced : undefined },
    { shouldRetryOnError: false, revalidateOnFocus: false },
  );
  const results = shouldQuery ? data?.items ?? [] : [];

  useEffect(() => {
    setActiveIndex(0);
  }, [debounced]);

  // Close on outside click.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const choose = useCallback(
    (personId: string) => {
      trackPeopleEvent("personSearch.topBar.used", { person_id: personId });
      setOpen(false);
      setValue("");
      navigate(`/people/${personId}`);
    },
    [navigate],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (results.length === 0) return;
      setActiveIndex((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (results.length === 0) return;
      setActiveIndex((i) => (i - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const pick = results[activeIndex];
      if (pick) choose(pick.id);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  if (!enabled || !accepted) {
    // Render the disabled visual from the old placeholder so the
    // top bar layout doesn't shift when the People feature is off.
    return (
      <div className="hidden sm:block relative">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-neutral-400)] pointer-events-none"
          aria-hidden="true"
        />
        <input
          type="text"
          placeholder={t("topbar.search.placeholder")}
          disabled
          className="w-[280px] h-9 pl-9 pr-3 rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-[var(--color-neutral-50)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-900)] placeholder:text-[var(--color-neutral-400)] outline-none opacity-50 cursor-not-allowed"
          aria-label={t("topbar.search.ariaLabel")}
        />
      </div>
    );
  }

  return (
    <div ref={containerRef} className="hidden sm:block relative">
      <Search
        size={16}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-neutral-400)] pointer-events-none"
        aria-hidden="true"
      />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={t("topBar.personSearch.placeholder")}
        aria-label={t("topBar.personSearch.placeholder")}
        aria-expanded={open}
        aria-controls="topbar-person-search-results"
        aria-autocomplete="list"
        role="combobox"
        data-testid="topbar-person-search"
        className="w-[280px] h-9 pl-9 pr-3 rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-[var(--color-white)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-900)] placeholder:text-[var(--color-neutral-400)] outline-none focus:border-[var(--color-primary)]"
      />

      {open && shouldQuery && (
        <ul
          id="topbar-person-search-results"
          role="listbox"
          data-testid="topbar-person-search-results"
          className="absolute left-0 right-0 mt-1 rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-[var(--color-white)] shadow-[var(--shadow-lg)] max-h-80 overflow-y-auto z-40"
        >
          {results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-[var(--color-neutral-500)]">
              {t("topBar.personSearch.noResults")}
            </li>
          ) : (
            results.map((p, i) => (
              <li key={p.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={i === activeIndex}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(p.id);
                  }}
                  className={[
                    "w-full flex items-center gap-2 px-3 py-2 text-left text-sm",
                    i === activeIndex
                      ? "bg-[var(--color-primary-surface)]"
                      : "hover:bg-[var(--color-neutral-50)]",
                  ].join(" ")}
                >
                  <PersonAvatar
                    person={{ id: p.id, display_name: p.display_name }}
                    size="sm"
                  />
                  <span className="truncate">{p.display_name}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
