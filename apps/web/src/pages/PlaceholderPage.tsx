interface PlaceholderPageProps {
  title: string;
  disabled?: boolean;
}

export default function PlaceholderPage({
  title,
  disabled,
}: PlaceholderPageProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <h2 className="text-[var(--text-h2-size)] leading-[var(--text-h2-height)] font-[var(--text-h2-weight)] text-[var(--color-neutral-900)]">
        {title}
      </h2>
      {disabled ? (
        <p className="mt-2 text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-400)]">
          Coming in a future update
        </p>
      ) : (
        <p className="mt-2 text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-500)]">
          Content will appear here soon
        </p>
      )}
    </div>
  );
}
