import type { Card, EventPayload, ReminderPayload, StatusPayload } from "../api/client";
import EventCard from "./EventCard";
import ReminderCard from "./ReminderCard";
import StatusCard from "./StatusCard";

interface CardRendererProps {
  card: Card;
}

export default function CardRenderer({ card }: CardRendererProps) {
  switch (card.type) {
    case "event":
      return <EventCard payload={card.payload as EventPayload} priorityScore={card.priority_score} />;
    case "reminder":
      return <ReminderCard payload={card.payload as ReminderPayload} />;
    case "status":
      return <StatusCard payload={card.payload as StatusPayload} />;
    default:
      return null;
  }
}
