/**
 * PersonCard — feed-friendly render of a trusted_person (S13-009).
 *
 * Shows up in Today (Sprint 13 context: seen_recently), Search
 * (context: search_match), and anywhere else the backend emits a
 * ``PersonCard`` envelope. Clicking navigates to the person detail
 * page and fires a metrics event so surface attribution is tracked.
 */

import { useNavigate } from "react-router-dom";

import { Card } from "../../design-system/components";
import PersonAvatar from "../people/PersonAvatar";
import type { PersonPayload } from "../../api/client";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";

interface PersonCardProps {
  id: string;
  payload: PersonPayload;
  /** Which surface rendered this card — used for metric attribution. */
  surface?: "today" | "search" | "other";
}

function contextDescription(payload: PersonPayload): string {
  const name = payload.display_name;
  const supporting =
    (payload.supporting_data as Record<string, unknown> | undefined) ?? {};
  switch (payload.context) {
    case "seen_recently": {
      const count = Number(supporting.recent_photo_count ?? 0);
      const days = Number(supporting.recent_days ?? 14);
      return t("today.person.seenRecently", { count, days });
    }
    case "upcoming_event": {
      const when =
        typeof supporting.when === "string" ? supporting.when : "soon";
      return t("today.person.upcomingEvent", { name, when });
    }
    case "catch_up": {
      const days = Number(supporting.days_since ?? 30);
      return t("today.person.catchUp", { name, days });
    }
    case "search_match":
    default:
      return t("search.result.person", { name });
  }
}

export default function PersonCard({
  id,
  payload,
  surface = "other",
}: PersonCardProps) {
  const navigate = useNavigate();
  const personId = payload.person_id ?? id;

  const handleClick = () => {
    if (surface === "today") trackPeopleEvent("personCard.clickedFromToday");
    else if (surface === "search")
      trackPeopleEvent("personCard.clickedFromSearch");
    navigate(`/people/${personId}`);
  };

  return (
    <Card onClick={handleClick}>
      <div className="flex items-center gap-[var(--space-3)]">
        <PersonAvatar
          person={{ id: personId, display_name: payload.display_name }}
          size="md"
        />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)] truncate">
            {payload.display_name}
          </p>
          <p className="mt-[var(--space-1)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)] truncate">
            {contextDescription(payload)}
          </p>
        </div>
      </div>
    </Card>
  );
}
