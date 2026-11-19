import { ClipboardList } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type {
  Building,
  Category,
  LostReport,
  LostReportStatus,
  MatchPage,
  Page,
  ProcessingStatus,
} from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote, useVisiblePolling } from "../api/useRemote";
import {
  Dialog,
  ErrorState,
  Loading,
  Pagination,
  Status,
} from "../ui/controls";
import { dateTime, localName } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";

function ReportStatus({ status }: { status: LostReportStatus }) {
  const { t } = useSession();
  return (
    <span
      className={ui.badge}
      data-status={
        status === "RESOLVED"
          ? "COLLECTED"
          : status === "CLOSED"
            ? "EXPIRED"
            : "POSTED"
      }
    >
      {
        {
          OPEN: t("진행 중", "Open"),
          RESOLVED: t("해결 완료", "Resolved"),
          CLOSED: t("자동 종료", "Closed"),
        }[status]
      }
    </span>
  );
}

function MatchStatus({ status }: { status: ProcessingStatus }) {
  const { t } = useSession();
  return (
    <span
      className={ui.badge}
      data-status={
        status === "READY"
          ? "COLLECTED"
          : status === "FAILED"
            ? "EXPIRED"
            : "POSTED"
      }
    >
      {
        {
          PENDING: t("매칭 대기", "Matching queued"),
          PROCESSING: t("매칭 진행 중", "Matching in progress"),
          READY: t("매칭 완료", "Matching complete"),
          FAILED: t("매칭 실패", "Matching failed"),
        }[status]
      }
    </span>
  );
}

function ReportCard({
  report,
  buildings,
}: {
  report: LostReport;
  buildings: Building[];
}) {
  const { t } = useSession();
  const path = "/lost-reports/" + report.reportId;
  const open = report.status === "OPEN";
  const matches = useRemote<MatchPage>(open ? path + "/matches?size=1" : null);
  const codes = report.possibleBuildingIds
    .map((id) => buildings.find((building) => building.buildingId === id)?.code)
    .filter(Boolean)
    .join(", ");
  return (
    <article>
      <span className={ui.reportStatus}>
        {open
          ? t("찾는 중", "Searching")
          : report.status === "RESOLVED"
            ? t("해결 완료", "Resolved")
            : t("자동 종료", "Closed")}
      </span>
      <h3 className={ui.reportTitle}>{report.description}</h3>
      <div className={ui.reportMeta}>
        {codes && (
          <p>
            {t("분실 추정 건물", "Possible buildings")} · {codes}
          </p>
        )}
        <p>
          {t("분실 기간", "Lost between")} · {report.lostDateFrom} ~{" "}
          {report.lostDateTo}
        </p>
      </div>
      {open && (
        <Link to={path + "/matches"} className={ui.reportStatus}>
          {matches.data?.totalElements
            ? t(
                "매칭 후보 " + matches.data.totalElements + "개",
                matches.data.totalElements + " match candidates",
              )
            : t("매칭 후보 보기", "View match candidates")}
        </Link>
      )}
      <Link to={path} className={ui.secondary + " " + ui.full}>
        {t("신고 관리하기", "Manage report")}
      </Link>
    </article>
  );
}

export default function LostReports() {
  const { t } = useSession();
  const [page, setPage] = useState(0);
  const reports = useRemote<Page<LostReport>>("/lost-reports?page=" + page);
  const buildings = useRemote<{ items: Building[] }>("/buildings", true);
  const activeCount = useRemote<Page<LostReport>>(
    (reports.data?.totalPages ?? 0) > 1
      ? "/lost-reports?status=OPEN&size=1"
      : null,
  );
  const active =
    reports.data?.items.filter(({ status }) => status === "OPEN") ?? [];
  const previous =
    reports.data?.items.filter(({ status }) => status !== "OPEN") ?? [];
  return (
    <div className={ui.formPage + " " + ui.reportPage}>
      <SectionTitle title={t("분실 신고", "Lost reports")} />
      {reports.loading && <Loading />}
      {reports.error !== undefined && (
        <ErrorState error={reports.error} retry={reports.reload} />
      )}
      {reports.data?.items.length === 0 && (
        <section className={ui.panel + " " + ui.emptyCard}>
          <ClipboardList size={34} strokeWidth={1.65} aria-hidden="true" />
          <h2>{t("분실 신고 내역이 없어요", "No lost reports yet")}</h2>
          <p>
            {t(
              "분실한 물품을 등록하면 매칭 알림을 받을 수 있어요.",
              "Report a lost item to receive match notifications.",
            )}
          </p>
        </section>
      )}
      {active.length > 0 && (
        <section className={ui.panel + " " + ui.reportGroup}>
          <div className={ui.between}>
            <h2>{t("진행 중인 분실 신고", "Active lost reports")}</h2>
            <span className={ui.reportCount}>
              {activeCount.data?.totalElements ?? active.length}
              {t("건", " reports")}
            </span>
          </div>
          {active.map((report) => (
            <ReportCard
              key={report.reportId}
              report={report}
              buildings={buildings.data?.items ?? []}
            />
          ))}
        </section>
      )}
      {previous.length > 0 && (
        <section className={ui.panel + " " + ui.reportGroup}>
          <h2>{t("이전 분실 신고", "Previous lost reports")}</h2>
          {previous.map((report) => (
            <ReportCard
              key={report.reportId}
              report={report}
              buildings={buildings.data?.items ?? []}
            />
          ))}
        </section>
      )}
      {reports.data && (
        <Pagination
          page={page}
          total={reports.data.totalPages}
          change={setPage}
        />
      )}
      <div className={ui.reportFooter}>
        <Link to="/lost-reports/new" className={ui.primary + " " + ui.full}>
          {t("새 분실 신고하기", "New lost report")}
        </Link>
      </div>
    </div>
  );
}

export function LostDetail({ created = false }: { created?: boolean }) {
  const { reportId } = useParams();
  const { api, user, t, lang } = useSession();
  const path = "/lost-reports/" + reportId;
  const result = useRemote<LostReport>(path);
  const categories = useRemote<{ items: Category[] }>("/categories", true);
  const buildings = useRemote<{ items: Building[] }>("/buildings", true);
  const [confirm, setConfirm] = useState<"extend" | "resolve">();
  const action = useAction();
  const report = result.data;
  if (result.error !== undefined)
    return <ErrorState error={result.error} retry={result.reload} />;
  if (!report) return <Loading />;
  const category = categories.data?.items.find(
    (value) => value.categoryId === report.categoryId,
  );
  const names = report.possibleBuildingIds
    .map((id) => {
      const building = buildings.data?.items.find(
        (value) => value.buildingId === id,
      );
      return building
        ? building.code + " · " + localName(building, lang)
        : t("이전에 선택한 건물", "Previously selected building");
    })
    .join(", ");
  const canEdit = report.status === "OPEN" && report.ownerId === user?.userId;
  const maxed =
    new Date(report.expiresAt).getTime() -
      new Date(report.createdAt).getTime() >=
    210 * 86400000;
  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={t("분실 신고", "Lost report")}
        back="/lost-reports"
      />
      <section className={ui.panel + " " + ui.stack}>
        {created && (
          <h2>{t("분실 신고 등록을 완료했어요", "Lost report submitted")}</h2>
        )}
        <div className={ui.between}>
          <h2 className={ui.userText}>{report.description}</h2>
          <ReportStatus status={report.status} />
        </div>
        {category && <p>{localName(category, lang)}</p>}
        <p>{names}</p>
        <p>
          {report.lostDateFrom} ~ {report.lostDateTo}
        </p>
        <p className={ui.muted}>
          {t("신고 기한", "Report expires")} ·{" "}
          {dateTime(report.expiresAt, lang)} KST
        </p>
        {report.privateIdentifyingDetails && (
          <div className={ui.notice + " " + ui.stack}>
            <h3>{t("비공개 식별 정보", "Private identifying details")}</h3>
            <p className={ui.userText}>{report.privateIdentifyingDetails}</p>
          </div>
        )}
        <Link className={ui.primary} to={path + "/matches"}>
          {t("매칭 후보 보기", "View match candidates")}
        </Link>
        {canEdit && (
          <div className={ui.row}>
            <Link className={ui.secondary} to={path + "/edit"}>
              {t("수정", "Edit")}
            </Link>
            <button
              className={ui.secondary}
              type="button"
              disabled={maxed}
              onClick={() => {
                action.clear();
                setConfirm("extend");
              }}
            >
              {t("30일 연장", "Extend by 30 days")}
            </button>
            <button
              className={ui.secondary}
              type="button"
              onClick={() => {
                action.clear();
                setConfirm("resolve");
              }}
            >
              {t("해결 완료", "Mark resolved")}
            </button>
          </div>
        )}
        {canEdit && maxed && (
          <p className={ui.muted}>
            {t(
              "신고의 최대 유효기간에 도달했어요.",
              "This report has reached its maximum duration.",
            )}
          </p>
        )}
      </section>
      {confirm && (
        <Dialog
          title={
            confirm === "extend"
              ? t("분실 신고를 연장할까요?", "Extend this report?")
              : t("분실 신고를 해결 처리할까요?", "Mark this report resolved?")
          }
          close={() => {
            if (!action.busy) setConfirm(undefined);
          }}
        >
          <div className={ui.stack}>
            {confirm === "resolve" && (
              <p>
                {t(
                  "신고를 종료하면 매칭 알림이 중지되고 비공개 식별 정보가 삭제돼요.",
                  "Resolving stops match notifications and deletes private identifying details.",
                )}
              </p>
            )}
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              className={ui.primary}
              type="button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await api.request(path + "/" + confirm, { method: "POST" });
                  setConfirm(undefined);
                  result.reload();
                })
              }
            >
              {confirm === "extend"
                ? t("연장", "Extend")
                : t("해결 완료", "Resolve")}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

export function Matches() {
  const { reportId } = useParams();
  const { t, lang } = useSession();
  const [page, setPage] = useState(0);
  const path = "/lost-reports/" + reportId;
  const reports = useRemote<LostReport>(path);
  const remote = useRemote<MatchPage>(path + "/matches?page=" + page);
  const buildings = useRemote<{ items: Building[] }>("/buildings", true);
  const matches = remote.data;
  const pending =
    matches?.matchingStatus === "PROCESSING" ||
    matches?.matchingStatus === "PENDING";
  useVisiblePolling(remote.reload, pending);

  return (
    <div className={ui.formPage}>
      <SectionTitle title={t("매칭 후보", "Match candidates")} back={path} />
      {reports.data && (
        <h2 className={ui.userText}>{reports.data.description}</h2>
      )}
      {remote.loading && <Loading />}
      {remote.error !== undefined && (
        <ErrorState error={remote.error} retry={remote.reload} />
      )}
      {matches && (
        <>
          <div className={ui.between}>
            <MatchStatus status={matches.matchingStatus} />
            <button
              className={ui.textButton}
              type="button"
              onClick={remote.reload}
            >
              {t("새로고침", "Refresh")}
            </button>
          </div>
          {pending && (
            <p className={ui.notice} role="status">
              {t(
                "비교 중이에요. 후보가 더 추가될 수 있어요.",
                "Matching is in progress and may find more candidates.",
              )}
            </p>
          )}
          {matches.matchingStatus === "FAILED" && (
            <p className={ui.notice} role="status">
              {t(
                "일부 정보를 비교하지 못했어요. 아래 결과는 현재 확인된 후보예요.",
                "Some information could not be matched. These are the candidates currently available.",
              )}
            </p>
          )}
          {matches.isComplete && matches.items.length === 0 && (
            <p className={ui.empty}>
              {t("일치하는 후보가 없어요.", "No match candidates yet.")}
            </p>
          )}
          {matches.items.map((match) => {
            const building = buildings.data?.items.find(
              (value) => value.buildingId === match.item.foundBuildingId,
            );
            return (
              <Link
                key={match.candidateId}
                to={"/found-items/" + match.itemId}
                className={ui.panel + " " + ui.stack}
              >
                <div className={ui.between}>
                  <h2>{match.item.title}</h2>
                  <Status status={match.item.status} />
                </div>
                <p className={ui.muted}>
                  {building && building.code + " · "}
                  {dateTime(match.item.foundAt, lang)} KST
                </p>
                <div className={ui.row}>
                  {match.matchedBy.map((reason) => (
                    <span key={reason} className={ui.badge}>
                      {reason === "BUILDING"
                        ? t("건물 일치", "Building match")
                        : t("키워드 일치", "Keyword match")}
                    </span>
                  ))}
                </div>
              </Link>
            );
          })}
          <Pagination page={page} total={matches.totalPages} change={setPage} />
        </>
      )}
    </div>
  );
}
