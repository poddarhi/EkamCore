import { Link } from "react-router-dom";
import { t } from "../i18n";

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--color-neutral-50)] text-center px-4">
      <h1 className="text-[var(--text-display-size)] leading-[var(--text-display-height)] font-[var(--text-display-weight)] text-[var(--color-neutral-900)]">
        {t("notFound.code")}
      </h1>
      <p className="mt-2 text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-500)]">
        {t("notFound.message")}
      </p>
      <Link
        to="/today"
        className="mt-6 text-[var(--color-primary-light)] hover:text-[var(--color-primary)] text-[var(--text-body-size)] underline transition-colors duration-[var(--duration-normal)]"
      >
        {t("notFound.backToToday")}
      </Link>
    </div>
  );
}
