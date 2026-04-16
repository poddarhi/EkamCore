/**
 * FollowUpCard — PLA follow-up suggestion in the Today feed (S14-009).
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";

import { Card } from "../../design-system/components";
import Button from "../../design-system/components/Button";
import Toast from "../Toast";
import { packCardsApi, type AcknowledgeAction } from "../../api/packCards";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";
import SnoozePicker from "./SnoozePicker";

interface FollowUpCardProps {
  cardId: string;
  payload: Record<string, unknown>;
  onAcknowledged?: () => void;
}

export default function FollowUpCard({
  cardId,
  payload,
  onAcknowledged,
}: FollowUpCardProps) {
  const navigate = useNavigate();
  const [toast, setToast] = useState<string | null>(null);
  const [showSnooze, setShowSnooze] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const name = (payload.person_display_name as string) ?? "Someone";
  const personId = payload.person_id as string | undefined;
  const days = Number(payload.days_since_last_interaction ?? 0);
  const context = (payload.last_interaction_context as string) ?? "";

  const ack = async (action: AcknowledgeAction, snoozedUntil?: string) => {
    setSubmitting(true);
    try {
      await packCardsApi.acknowledge(cardId, action, snoozedUntil);
      trackPeopleEvent(
        `packCard.follow_up.${action}` as never,
        { card_id: cardId },
      );
      setToast(t(`packCard.acknowledged.${action}`));
      onAcknowledged?.();
    } catch {
      setToast(t("error.generic"));
    } finally {
      setSubmitting(false);
      setShowSnooze(false);
    }
  };

  return (
    <>
      <Card>
        <div className="flex items-start gap-3" role="article" aria-label={t("packCard.followUp.title", { name })}>
          <UserPlus size={20} className="text-[var(--color-primary)] shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-[var(--text-body-size)]">
              {t("packCard.followUp.title", { name })}
            </p>
            <p className="text-[var(--text-small-size)] text-[var(--color-neutral-600)] mt-1">
              {t("packCard.followUp.body", { days, context })}
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
                {t("packCard.followUp.actionDone")}
              </Button>
              <Button variant="ghost" size="sm" loading={submitting} onClick={() => void ack("dismissed")}>
                {t("packCard.followUp.actionDismiss")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setShowSnooze(!showSnooze)}>
                {t("packCard.followUp.actionSnooze")}
              </Button>
            </div>
            {showSnooze && (
              <SnoozePicker
                onPick={(date) => void ack("snoozed", date)}
                onCancel={() => setShowSnooze(false)}
              />
            )}
          </div>
        </div>
      </Card>
      {toast && <Toast message={toast} variant="success" onDismiss={() => setToast(null)} />}
    </>
  );
}
