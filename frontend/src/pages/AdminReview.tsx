import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { Page, PostReport } from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { ErrorState, Loading, Pagination } from "../ui/controls";
import { kstDateTime } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";
import styles from "./admin.module.css";
import type { AdminDispute } from "./adminTypes";

type Moderation = PostReport | AdminDispute;
type Kind = "post-reports" | "disputes";

function caseId(entry: Moderation) {
  return "reportId" in entry ? entry.reportId : entry.disputeId;
}

function ReviewStatus({ status }: { status: Moderation["status"] }) {
  const { t } = useSession();
  const open = status === "OPEN";
  return (
    <span className={ui.badge} data-status={open ? "POSTED" : "COLLECTED"}>
      {open ? t("검토 대기", "Awaiting review") : t("검토 완료", "Reviewed")}
    </span>
  );
}

export function ReviewQueue({ kind }: { kind: Kind }) {
  const { t, lang } = useSession();
  const [page, setPage] = useState(0);
  const [status, setStatus] = useState("OPEN");
  const reviewed = kind === "post-reports" ? "REVIEWED" : "RESOLVED";
  const path = "/admin/" + kind;
  const records = useRemote<Page<Moderation>>(
    path + "?page=" + page + "&status=" + status,
  );

  return (
    <div className={ui.stack}>
      <select
        className={styles.reviewFilter}
        aria-label={t("검토 상태", "Review status")}
        value={status}
        onChange={(event) => {
          setStatus(event.target.value);
          setPage(0);
        }}
      >
        <option value="OPEN">{t("검토 대기", "Awaiting review")}</option>
        <option value={reviewed}>{t("검토 완료", "Reviewed")}</option>
      </select>
      {records.loading && <Loading />}
      {records.error !== undefined && (
        <ErrorState error={records.error} retry={records.reload} />
      )}
      {records.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("표시할 건이 없어요.", "No cases to show.")}
        </p>
      )}
      {records.data?.items.map((entry) => (
        <Link
          className={ui.panel + " " + ui.stack}
          to={path + "/" + caseId(entry)}
          key={caseId(entry)}
        >
          <div className={ui.between}>
            <strong className={ui.userText}>
              {"details" in entry ? entry.details : entry.reason}
            </strong>
            <ReviewStatus status={entry.status} />
          </div>
          <small className={ui.muted}>
            {kstDateTime(entry.createdAt, lang)}
          </small>
        </Link>
      ))}
      {records.data && (
        <Pagination
          page={page}
          total={records.data.totalPages}
          change={setPage}
        />
      )}
    </div>
  );
}

function ReviewForm({
  record,
  path,
  reload,
}: {
  record: Moderation;
  path: string;
  reload: () => void;
}) {
  const { t, api } = useSession();
  const isReport = "reportId" in record;
  const [decision, setDecision] = useState(isReport ? "DISMISS" : "DISMISSED");
  const [block, setBlock] = useState(false);
  const action = useAction();
  return (
    <form
      className={ui.panel + " " + ui.stack}
      onSubmit={(event) => {
        event.preventDefault();
        void action.run(async () => {
          const body = isReport
            ? { decision }
            : { decision, blockCollector: decision === "UPHELD" && block };
          await api.request(path + "/review", { method: "POST", body });
          reload();
        });
      }}
    >
      <label className={ui.field}>
        {t("검토 결과", "Decision")}
        <select
          value={decision}
          onChange={(event) => setDecision(event.target.value)}
        >
          {isReport ? (
            <>
              <option value="DISMISS">
                {t("신고 기각", "Dismiss report")}
              </option>
              <option value="HIDE">{t("게시물 숨김", "Hide post")}</option>
            </>
          ) : (
            <>
              <option value="DISMISSED">
                {t("이의 기각", "Dismiss dispute")}
              </option>
              <option value="UPHELD">{t("이의 인정", "Uphold dispute")}</option>
            </>
          )}
        </select>
      </label>
      {!isReport && decision === "UPHELD" && (
        <label className={ui.row}>
          <input
            type="checkbox"
            checked={block}
            onChange={(event) => setBlock(event.target.checked)}
          />
          {t(
            "수거자의 수거 권한 제한",
            "Restrict this member from collecting items",
          )}
        </label>
      )}
      {action.error !== undefined && <ErrorState error={action.error} />}
      <button type="submit" className={ui.primary} disabled={action.busy}>
        {t("검토 결과 저장", "Save decision")}
      </button>
    </form>
  );
}

function RestrictFromDispute({ record }: { record: AdminDispute }) {
  const { t, api } = useSession();
  const [saved, setSaved] = useState(false);
  const action = useAction();
  if (record.decision !== "UPHELD") return null;
  return (
    <section className={ui.panel + " " + ui.stack}>
      <button
        className={ui.danger}
        type="button"
        disabled={action.busy || saved}
        onClick={() =>
          void action.run(async () => {
            await api.request(
              "/admin/users/" + record.collectorId + "/collection-restriction",
              {
                method: "PUT",
                body: { restricted: true, disputeId: record.disputeId },
              },
            );
            setSaved(true);
          })
        }
      >
        {t(
          "이 분쟁으로 수거 권한 제한",
          "Restrict collection based on this dispute",
        )}
      </button>
      {action.error !== undefined && <ErrorState error={action.error} />}
      {saved && (
        <p className={ui.notice} role="status">
          {t("수거 권한을 제한했어요.", "Collection access restricted.")}
        </p>
      )}
    </section>
  );
}

export default function AdminReviewDetail({ kind }: { kind: Kind }) {
  const { t, lang } = useSession();
  const { caseId } = useParams();
  const path = "/admin/" + kind + "/" + caseId;
  const result = useRemote<Moderation>(path);
  const record = result.data;
  if (result.error !== undefined)
    return <ErrorState error={result.error} retry={result.reload} />;
  if (!record) return <Loading />;
  const reasons = {
    INAPPROPRIATE: t("부적절", "Inappropriate"),
    SPAM: t("스팸", "Spam"),
    OTHER: t("기타", "Other"),
  };
  const decisions = {
    HIDE: t("숨김", "Hidden"),
    DISMISS: t("기각", "Dismissed"),
    UPHELD: t("인정", "Upheld"),
    DISMISSED: t("기각", "Dismissed"),
  };

  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={
          kind === "post-reports"
            ? t("게시물 신고 검토", "Post report review")
            : t("수거 분쟁 검토", "Collection dispute review")
        }
        back={"/admin/" + kind}
      />
      <article className={ui.panel + " " + ui.stack}>
        <div className={ui.between}>
          <strong>{t("접수 내역", "Case details")}</strong>
          <ReviewStatus status={record.status} />
        </div>
        <p className={ui.userText}>
          {"details" in record ? record.details : record.reason}
        </p>
        {"reasonCode" in record && <p>{reasons[record.reasonCode]}</p>}
        <p className={ui.muted}>{kstDateTime(record.createdAt, lang)}</p>
        {record.decision && (
          <p>
            {t("검토 결과", "Decision")} · {decisions[record.decision]}
          </p>
        )}
        <Link to={"/found-items/" + record.itemId} className={ui.secondary}>
          {t("물품 상세", "View item")}
        </Link>
      </article>
      {record.status === "OPEN" && (
        <ReviewForm
          key={"review:" + caseId}
          record={record}
          path={path}
          reload={result.reload}
        />
      )}
      {"collectorId" in record && (
        <RestrictFromDispute key={"restriction:" + caseId} record={record} />
      )}
    </div>
  );
}
