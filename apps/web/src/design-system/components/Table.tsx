import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";
import type { ReactNode } from "react";

type SortDirection = "asc" | "desc" | null;

interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  width?: string;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  sortColumn?: string;
  sortDirection?: SortDirection;
  onSort?: (column: string) => void;
  rowKey: (row: T) => string;
}

function SortIcon({ direction }: { direction: SortDirection }) {
  if (direction === "asc") return <ChevronUp size={14} aria-hidden="true" />;
  if (direction === "desc") return <ChevronDown size={14} aria-hidden="true" />;
  return <ChevronsUpDown size={14} className="opacity-40" aria-hidden="true" />;
}

export default function Table<T extends Record<string, unknown>>({
  columns,
  data,
  sortColumn,
  sortDirection,
  onSort,
  rowKey,
}: TableProps<T>) {
  return (
    <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)]">
      <table className="w-full text-[var(--text-body-size)]">
        <thead className="sticky top-0 bg-[var(--color-neutral-50)] border-b border-[var(--color-neutral-200)]">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                style={col.width ? { width: col.width } : undefined}
                className={[
                  "px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider",
                  col.sortable && onSort ? "cursor-pointer select-none hover:text-[var(--color-neutral-700)]" : "",
                ].join(" ")}
                onClick={col.sortable && onSort ? () => onSort(col.key) : undefined}
                aria-sort={
                  col.key === sortColumn && sortDirection
                    ? sortDirection === "asc" ? "ascending" : "descending"
                    : undefined
                }
              >
                <span className="inline-flex items-center gap-1">
                  {col.header}
                  {col.sortable && <SortIcon direction={col.key === sortColumn ? sortDirection ?? null : null} />}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-[var(--space-4)] py-[var(--space-8)] text-center text-[var(--text-small-size)] text-[var(--color-neutral-400)]"
              >
                No data available
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={rowKey(row)}
                className={[
                  "border-b border-[var(--color-neutral-100)] last:border-b-0",
                  i % 2 === 1 ? "bg-[var(--color-neutral-50)]" : "bg-[var(--color-white)]",
                  "hover:bg-[var(--color-primary-surface)] transition-colors duration-[var(--duration-fast)]",
                ].join(" ")}
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-[var(--space-4)] py-[var(--space-3)] text-[var(--color-neutral-900)]">
                    {col.render ? col.render(row) : String(row[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
