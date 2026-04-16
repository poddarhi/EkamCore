import type {
  Card,
  EventPayload,
  ReminderPayload,
  StatusPayload,
  FilePayload,
  PersonPayload,
  PhotoPayload,
} from "../api/client";
import EventCard from "./EventCard";
import ReminderCard from "./ReminderCard";
import StatusCard from "./StatusCard";
import FileCard from "./cards/FileCard";
import FollowUpCard from "./cards/FollowUpCard";
import PersonCard from "./cards/PersonCard";
import PhotoCard from "./cards/PhotoCard";
import RelationshipReminderCard from "./cards/RelationshipReminderCard";
import WeeklySummaryCard from "./cards/WeeklySummaryCard";

interface CardRendererProps {
  card: Card;
  query?: string;
  /** Surface that rendered the card — passed to PersonCard for
   *  metric attribution (today vs. search vs. other). */
  surface?: "today" | "search" | "other";
  /** Called when a pack card is acknowledged (done/dismissed/snoozed)
   *  so the parent can revalidate the feed. */
  onPackCardAcknowledged?: () => void;
}

export default function CardRenderer({
  card,
  query = "",
  surface = "other",
  onPackCardAcknowledged,
}: CardRendererProps) {
  switch (card.type) {
    case "event":
      return (
        <EventCard
          payload={card.payload as EventPayload}
          priorityScore={card.priority_score}
        />
      );
    case "reminder":
      return <ReminderCard payload={card.payload as ReminderPayload} />;
    case "status":
      return <StatusCard payload={card.payload as StatusPayload} />;
    case "file":
      return (
        <FileCard
          id={card.id}
          payload={card.payload as FilePayload}
          query={query}
        />
      );
    case "photo":
      return <PhotoCard id={card.id} payload={card.payload as PhotoPayload} />;
    case "person":
      return (
        <PersonCard
          id={card.id}
          payload={card.payload as PersonPayload}
          surface={surface}
        />
      );
    case "pack": {
      // Discriminate pack card subtypes via the card_type field in the
      // payload (set by PackCardSource in the Today assembly).
      const packPayload = card.payload as Record<string, unknown>;
      const cardType = packPayload.card_type as string | undefined;
      const packCardId = (packPayload.pack_card_id as string) ?? card.id;
      if (cardType === "follow_up_suggestion") {
        return (
          <FollowUpCard
            cardId={packCardId}
            payload={packPayload}
            onAcknowledged={onPackCardAcknowledged}
          />
        );
      }
      if (cardType === "weekly_summary") {
        return (
          <WeeklySummaryCard
            cardId={packCardId}
            payload={packPayload}
            onAcknowledged={onPackCardAcknowledged}
          />
        );
      }
      if (cardType === "relationship_reminder") {
        return (
          <RelationshipReminderCard
            cardId={packCardId}
            payload={packPayload}
            onAcknowledged={onPackCardAcknowledged}
          />
        );
      }
      return null;
    }
    default:
      return null;
  }
}
