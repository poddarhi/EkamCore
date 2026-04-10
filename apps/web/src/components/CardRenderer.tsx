import type { Card, EventPayload, ReminderPayload, StatusPayload, FilePayload, PhotoPayload } from "../api/client";
import EventCard from "./EventCard";
import ReminderCard from "./ReminderCard";
import StatusCard from "./StatusCard";
import FileCard from "./cards/FileCard";
import PhotoCard from "./cards/PhotoCard";

interface CardRendererProps {
  card: Card;
  query?: string;
}

export default function CardRenderer({ card, query = "" }: CardRendererProps) {
  switch (card.type) {
    case "event":
      return <EventCard payload={card.payload as EventPayload} priorityScore={card.priority_score} />;
    case "reminder":
      return <ReminderCard payload={card.payload as ReminderPayload} />;
    case "status":
      return <StatusCard payload={card.payload as StatusPayload} />;
    case "file":
      return <FileCard id={card.id} payload={card.payload as FilePayload} query={query} />;
    case "photo":
      return <PhotoCard id={card.id} payload={card.payload as PhotoPayload} />;
    default:
      return null;
  }
}
