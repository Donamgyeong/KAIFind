import { useState } from "react";
import { Navigate, NavLink, useParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { Page, Role } from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { Dialog, ErrorState, Loading, Pagination } from "../ui/controls";
import DateField from "../ui/DateField";
import { dateTime, statusLabel } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";
import AdminReference from "./AdminReference";
import { ReviewQueue } from "./AdminReview";
import { auditActions } from "./adminTypes";
import type { AdminUser, AuditLog, Statistics } from "./adminTypes";
import styles from "./admin.module.css";

function Overview() {
  const { t, lang } = useSession();
  const summary = useRemote<Statistics>("/admin/statistics");
  if (summary.error !== undefined)
    return <ErrorState error={summary.error} retry={summary.reload} />;
  if (!summary.data) return <Loading />;
  const { postedCount, collectedCount, expiredCount, asOf } = summary.data;

  return (
    <div className={ui.stack}>
      <h2>{t("물품 상태별 통계", "Items by status")}</h2>
      <div className={styles.metrics}>
        {(
          [
            ["POSTED", postedCount],
            ["COLLECTED", collectedCount],
            ["EXPIRED", expiredCount],
          ] as const
        ).map(([status, count]) => (
          <div key={status} className={ui.panel + " " + styles.metric}>
            <span className={ui.badge} data-status={status}>
              {statusLabel(status, t)}
            </span>
            <strong>{count.toLocaleString(lang)}</strong>
          </div>
        ))}
      </div>
      <small className={ui.muted}>
        {t("집계 시각", "As of")} {dateTime(asOf, lang)} KST
      </small>
    </div>
  );
}

function Users() {
  const { t, api, user, refreshUser } = useSession();
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<Role | "">("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<{
    member: AdminUser;
    action: "role" | "restriction";
  }>();
  const params = new URLSearchParams({
    page: String(page),
    ...(query ? { q: query } : {}),
    ...(role ? { role } : {}),
  });
  const members = useRemote<Page<AdminUser>>("/admin/users?" + params);
  const action = useAction();
  const roleLabel = (value: Role) =>
    value === "ADMIN" ? t("관리자", "Administrator") : t("회원", "Member");
  const nextRole = selected?.member.role === "ADMIN" ? "MEMBER" : "ADMIN";

  function choose(member: AdminUser, operation: "role" | "restriction") {
    action.clear();
    setSelected({ member, action: operation });
  }

  return (
    <div className={ui.stack}>
      <form
        className={styles.filters}
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(draft.trim());
          setPage(0);
        }}
      >
        <label className={ui.field}>
          {t("이름 검색", "Search by name")}
          <input
            type="search"
            maxLength={100}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <label className={ui.field}>
          {t("권한", "Role")}
          <select
            value={role}
            onChange={(event) => {
              setRole(event.target.value as typeof role);
              setPage(0);
            }}
          >
            <option value="">{t("전체", "All")}</option>
            <option value="MEMBER">{roleLabel("MEMBER")}</option>
            <option value="ADMIN">{roleLabel("ADMIN")}</option>
          </select>
        </label>
        <button className={ui.primary} type="submit">
          {t("검색", "Search")}
        </button>
      </form>
      {members.loading && <Loading />}
      {members.error !== undefined && (
        <ErrorState error={members.error} retry={members.reload} />
      )}
      {members.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("검색 결과가 없어요.", "No users found.")}
        </p>
      )}
      {members.data?.items.map((member) => (
        <article className={ui.panel + " " + ui.stack} key={member.userId}>
          <div className={ui.between}>
            <strong>{member.name}</strong>
            <span className={ui.badge}>{roleLabel(member.role)}</span>
          </div>
          {member.collectionRestricted && (
            <p className={ui.notice}>
              {t("수거 권한 제한 중", "Collection restricted")}
            </p>
          )}
          <div className={ui.row}>
            <button
              className={ui.secondary}
              type="button"
              onClick={() => choose(member, "role")}
            >
              {member.role === "ADMIN"
                ? t("관리자 회수", "Revoke administrator")
                : t("관리자 부여", "Grant administrator")}
            </button>
            {member.collectionRestricted && (
              <button
                className={ui.secondary}
                type="button"
                onClick={() => choose(member, "restriction")}
              >
                {t("수거 제한 해제", "Lift collection restriction")}
              </button>
            )}
          </div>
        </article>
      ))}
      {members.data && (
        <Pagination
          page={page}
          total={members.data.totalPages}
          change={setPage}
        />
      )}
      {selected && (
        <Dialog
          title={
            selected.action === "role"
              ? t("관리자 권한을 변경할까요?", "Change administrator access?")
              : t("수거 제한을 해제할까요?", "Lift the collection restriction?")
          }
          close={() => {
            if (!action.busy) setSelected(undefined);
          }}
        >
          <div className={ui.stack}>
            <p>
              {selected.member.name}
              {selected.action === "role" ? " · " + roleLabel(nextRole) : ""}
            </p>
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              className={ui.primary}
              type="button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  const path = "/admin/users/" + selected.member.userId;
                  if (selected.action === "role") {
                    await api.request(path + "/role", {
                      method: "PATCH",
                      body: { role: nextRole },
                    });
                    if (selected.member.userId === user?.userId)
                      await refreshUser();
                  } else {
                    await api.request(path + "/collection-restriction", {
                      method: "PUT",
                      body: { restricted: false },
                    });
                  }
                  setSelected(undefined);
                  members.reload();
                })
              }
            >
              {t("변경 적용", "Apply change")}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function Audit() {
  const { t, lang } = useSession();
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(0);
  const result = useRemote<Page<AuditLog>>(
    "/admin/audit-logs?page=" + page + filter,
  );
  return (
    <div className={ui.stack}>
      <form
        className={styles.filters}
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          const params = new URLSearchParams();
          for (const key of ["action", "actorId", "targetId", "from", "to"]) {
            const value = String(data.get(key) ?? "").trim();
            if (value)
              params.set(
                key,
                key === "from" || key === "to" ? value + ":00+09:00" : value,
              );
          }
          setFilter(params.size ? "&" + params.toString() : "");
          setPage(0);
        }}
      >
        <label className={ui.field}>
          {t("활동", "Action")}
          <select name="action" aria-label={t("활동", "Action")}>
            <option value="">{t("전체", "All")}</option>
            {auditActions.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className={ui.field}>
          {t("수행자 ID", "Actor ID")}
          <input name="actorId" maxLength={36} />
        </label>
        <label className={ui.field}>
          {t("대상 ID", "Target ID")}
          <input name="targetId" maxLength={36} />
        </label>
        <label className={ui.field}>
          {t("시작 시각 (KST)", "From (KST)")}
          <DateField
            label={t("시작 시각 (KST)", "From (KST)")}
            name="from"
            time
          />
        </label>
        <label className={ui.field}>
          {t("종료 시각 (KST)", "To (KST)")}
          <DateField label={t("종료 시각 (KST)", "To (KST)")} name="to" time />
        </label>
        <button className={ui.primary} type="submit">
          {t("조회", "Apply filters")}
        </button>
      </form>
      {result.loading && <Loading />}
      {result.error !== undefined && (
        <ErrorState error={result.error} retry={result.reload} />
      )}
      {result.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("감사 기록이 없어요.", "No audit logs found.")}
        </p>
      )}
      {result.data?.items.map((entry) => (
        <details
          className={ui.panel + " " + styles.auditRecord}
          key={entry.auditLogId}
        >
          <summary>
            <strong>{entry.action}</strong>
            <time dateTime={entry.occurredAt}>
              {dateTime(entry.occurredAt, lang)} KST
            </time>
          </summary>
          <dl>
            <dt>{t("수행자", "Actor")}</dt>
            <dd>
              {entry.actorType}
              {entry.actorId ? " · " + entry.actorId : ""}
            </dd>
            <dt>{t("대상", "Target")}</dt>
            <dd>
              {entry.targetType} · {entry.targetId}
            </dd>
          </dl>
          {!!Object.keys(entry.metadata).length && (
            <pre>{JSON.stringify(entry.metadata, null, 2)}</pre>
          )}
        </details>
      ))}
      {result.data && (
        <Pagination
          page={page}
          total={result.data.totalPages}
          change={setPage}
        />
      )}
    </div>
  );
}

export default function Admin() {
  const { t } = useSession();
  const { section = "overview" } = useParams();
  const sections = [
    { key: "overview", label: t("통계", "Statistics"), view: <Overview /> },
    { key: "users", label: t("회원·권한", "Users and roles"), view: <Users /> },
    {
      key: "buildings",
      label: t("건물", "Buildings"),
      view: <AdminReference kind="buildings" />,
    },
    {
      key: "categories",
      label: t("카테고리", "Categories"),
      view: <AdminReference kind="categories" />,
    },
    {
      key: "post-reports",
      label: t("게시물 신고", "Post reports"),
      view: <ReviewQueue kind="post-reports" />,
    },
    {
      key: "disputes",
      label: t("수거 분쟁", "Collection disputes"),
      view: <ReviewQueue kind="disputes" />,
    },
    { key: "audit", label: t("감사 로그", "Audit logs"), view: <Audit /> },
  ];
  const selected = sections.find(({ key }) => key === section);
  if (!selected) return <Navigate to="/admin" replace />;
  return (
    <div className={ui.stack}>
      <SectionTitle
        title={t("관리자 대시보드", "Admin dashboard")}
        back="/me"
      />
      <nav
        className={styles.tabs}
        aria-label={t("관리자 메뉴", "Admin sections")}
      >
        {sections.map(({ key, label }) => (
          <NavLink
            end
            key={key}
            to={key === "overview" ? "/admin" : "/admin/" + key}
            className={ui.chip}
            aria-current={section === key ? "page" : undefined}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <section key={section} aria-label={selected.label}>
        {selected.view}
      </section>
    </div>
  );
}
