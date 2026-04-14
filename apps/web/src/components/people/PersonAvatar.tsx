/**
 * PersonAvatar — face crop or deterministic-color initials (S13-002).
 *
 * Wraps the design-system Avatar. Tries the cropped face endpoint
 * first; on 404 or decode failure the underlying Avatar falls back
 * to initials automatically. The browser caches the 160px JPEG for
 * an hour (Cache-Control set server-side).
 */

import { useState } from "react";

import Avatar from "../../design-system/components/Avatar";
import type { TrustedPerson } from "../../types/people";

type PersonAvatarSize = "sm" | "md" | "lg" | "xl";

interface PersonAvatarProps {
  person: Pick<TrustedPerson, "id" | "display_name">;
  size?: PersonAvatarSize;
  showName?: boolean;
}

/** ART-05 avatar token sizes. The design-system Avatar only exposes
 * sm/md/lg/xl — for "xl" (160px) we fall back to lg (56px) because
 * Avatar doesn't support 160px natively yet. This story uses lg in
 * the card grid which matches the ART-05 spec closely enough; a
 * later story can extend the base component. */
const SIZE_MAP: Record<PersonAvatarSize, "sm" | "md" | "lg" | "xl"> = {
  sm: "sm",
  md: "md",
  lg: "lg",
  xl: "xl",
};

export default function PersonAvatar({
  person,
  size = "md",
  showName = false,
}: PersonAvatarProps) {
  // Track the set of person ids whose avatar endpoint failed so we
  // render initials for them even across re-renders. Using a Set in
  // state (instead of a single failed-id string) keeps grid cell
  // recycling from re-showing a broken img when the component remounts
  // against a different person id.
  const [failedIds, setFailedIds] = useState<Set<string>>(() => new Set());
  const candidateSrc = failedIds.has(person.id)
    ? null
    : `/api/v1/people/${person.id}/avatar`;

  const base = (
    <AvatarWithFallback
      src={candidateSrc}
      name={person.display_name}
      size={SIZE_MAP[size]}
      onError={() => {
        setFailedIds((prev) => {
          if (prev.has(person.id)) return prev;
          const next = new Set(prev);
          next.add(person.id);
          return next;
        });
      }}
    />
  );

  if (!showName) return base;
  return (
    <div className="flex items-center gap-2">
      {base}
      <span className="text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-800)]">
        {person.display_name}
      </span>
    </div>
  );
}

interface AvatarWithFallbackProps {
  src: string | null;
  name: string;
  size: "sm" | "md" | "lg" | "xl";
  onError: () => void;
}

/** Thin wrapper that exposes an onError hook. The design-system
 * Avatar doesn't forward `onError`, so we render a raw <img> when we
 * have a src candidate and fall through to Avatar for initials. */
function AvatarWithFallback({ src, name, size, onError }: AvatarWithFallbackProps) {
  if (src) {
    const px =
      size === "sm" ? 32 : size === "md" ? 40 : size === "lg" ? 56 : 80;
    return (
      <img
        src={src}
        alt={name}
        onError={onError}
        className="inline-flex items-center justify-center rounded-full overflow-hidden shrink-0 object-cover bg-[var(--color-primary-surface)]"
        style={{ width: px, height: px }}
      />
    );
  }
  return <Avatar name={name} size={size} />;
}
