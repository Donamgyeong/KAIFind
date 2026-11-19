import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../api/session-context";
import SectionTitle from "./SectionTitle";
import ui from "./ui.module.css";

export function ReportList({
  title,
  createTo,
  createLabel,
  children,
}: {
  title: string;
  createTo: string;
  createLabel: string;
  children: ReactNode;
}) {
  return (
    <div className={ui.formPage + " " + ui.reportPage}>
      <SectionTitle title={title} />
      {children}
      <div className={ui.reportFooter}>
        <Link className={ui.primary + " " + ui.full} to={createTo}>
          {createLabel}
        </Link>
      </div>
    </div>
  );
}

export function EmptyReportList({
  Icon,
  title,
  description,
}: {
  Icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <section className={ui.panel + " " + ui.emptyCard}>
      <Icon size={34} strokeWidth={1.65} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{description}</p>
    </section>
  );
}

export function ReportGroup({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: ReactNode;
}) {
  const { t } = useSession();
  return (
    <section className={ui.panel + " " + ui.reportGroup}>
      {count === undefined ? (
        <h2>{title}</h2>
      ) : (
        <div className={ui.between}>
          <h2>{title}</h2>
          <span className={ui.reportCount}>
            {count}
            {t("건", " reports")}
          </span>
        </div>
      )}
      {children}
    </section>
  );
}

export function ReportEntry({
  title,
  status,
  to,
  children,
}: {
  title: string;
  status: string;
  to: string;
  children: ReactNode;
}) {
  const { t } = useSession();
  return (
    <article>
      <span className={ui.reportStatus}>{status}</span>
      <h3 className={ui.reportTitle}>{title}</h3>
      {children}
      <Link className={ui.secondary + " " + ui.full} to={to}>
        {t("신고 관리하기", "Manage report")}
      </Link>
    </article>
  );
}
