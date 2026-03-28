import { User } from "lucide-react";

type AvatarSize = "sm" | "md" | "lg" | "xl";

interface AvatarProps {
  src?: string | null;
  name?: string;
  size?: AvatarSize;
}

const sizeMap: Record<AvatarSize, { px: number; iconPx: number; textClass: string }> = {
  sm: { px: 32, iconPx: 16, textClass: "text-[var(--text-caption-size)]" },
  md: { px: 40, iconPx: 20, textClass: "text-[var(--text-small-size)]" },
  lg: { px: 56, iconPx: 24, textClass: "text-[var(--text-h3-size)]" },
  xl: { px: 80, iconPx: 32, textClass: "text-[var(--text-h1-size)]" },
};

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

export default function Avatar({ src, name, size = "md" }: AvatarProps) {
  const { px, iconPx, textClass } = sizeMap[size];

  const baseClasses =
    "inline-flex items-center justify-center rounded-full overflow-hidden shrink-0 bg-[var(--color-primary-surface)] text-[var(--color-primary)]";

  if (src) {
    return (
      <img
        src={src}
        alt={name ?? "Avatar"}
        className={`${baseClasses} object-cover`}
        style={{ width: px, height: px }}
      />
    );
  }

  if (name) {
    return (
      <span
        className={`${baseClasses} font-semibold ${textClass}`}
        style={{ width: px, height: px }}
        aria-label={name}
      >
        {getInitials(name)}
      </span>
    );
  }

  return (
    <span
      className={baseClasses}
      style={{ width: px, height: px }}
      aria-label="User avatar"
    >
      <User size={iconPx} />
    </span>
  );
}
