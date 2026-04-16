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
import PersonCard from "./cards/PersonCard";
import PhotoCard from "./cards/PhotoCard";

interface CardRendererProps {
  card: Card;
  query?: string;
  /** Surface that rendered the card — passed to PersonCard for
   *  metric attribution (today vs. search vs. other). */
  surface?: "today" | "search" | "other";
}

export default function CardRenderer({
  card,
  query = "",
  surface = "other",
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
    default:
      return null;
  }
}
