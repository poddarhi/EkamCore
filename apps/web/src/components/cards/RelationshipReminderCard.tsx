/**
 * RelationshipReminderCard — PLA "reconnect with {name}" card (S14-009).
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heart } from "lucide-react";

import { Card } from "../../design-system/components";
import Button from "../../design-system/components/Button";
import Toast from "../Toast";
import { packCardsApi, type AcknowledgeAction } from "../../api/packCards";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";

interface RelationshipReminderCardProps {
  cardId: string;
  payload: Record<string, unknown>;
  onAcknowledged?: () => void;
}

export default function RelationshipReminderCard({
  cardId,
  payload,
  onAcknowledged,
}: RelationshipReminderCardProps) {
  const navigate = useNavigate();
  const [toast, setToast] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const name = (payload.person_display_name as string) ?? "Someone";
  const personId = payload.person_id as string | undefined;
  const days = Number(payload.days_since_last_interaction ?? 0);
  const context = (payload.relationship_context as string) ?? "";

  const ack = async (action: AcknowledgeAction) => {
    setSubmitting(true);
    try {
      await packCardsApi.acknowledge(cardId, action);
      trackPeopleEvent(
        `packCard.relationship_reminder.${action}` as never,
        { card_id: cardId },
      );
      setToast(t(`packCard.acknowledged.${action}`));
      onAcknowledged?.();
    } catch {
      setToast(t("error.generic"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Card>
        <div className="flex items-start gap-3" role="article" aria-label={t("packCard.relationshipReminder.title", { name })}>
          <Heart size={20} className="text-[var(--color-warning)] shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-[var(--text-body-size)]">
              {t("packCard.relationshipReminder.title", { name })}
            </p>
            <p className="text-[var(--text-small-size)] text-[var(--color-neutral-600)] mt-1">
              {t("packCard.relationshipReminder.body", { days })}
              {context ? ` · ${context}` : ""}
            </p>
            {personId && (
              <button
                type="button"
                onClick={() => navigate(`/people/${personId}`)}
                className="text-xs text-[var(--color-primary)] hover:underline mt-1"
              >
                View person
              </button>
            )}
            <div className="flex gap-2 mt-3">
              <Button variant="primary" size="sm" loading={submitting} onClick={() => void ack("done")}>
                {t("packCard.relationshipReminder.actionDone")}
              </Button>
              <Button variant="ghost" size="sm" loading={submitting} onClick={() => void ack("dismissed")}>
                {t("packCard.relationshipReminder.actionDismiss")}
              </Button>
            </div>
          </div>
        </div>
      </Card>
      {toast && <Toast message={toast} variant="success" onDismiss={() => setToast(null)} />}
    </>
  );
}
