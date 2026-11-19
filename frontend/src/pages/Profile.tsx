import { UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../api/session-context";
import type {
  Conversation,
  LostReport,
  NotificationSettings,
  Page,
  Subscription,
  User,
} from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { Dialog, ErrorState, Loading, Pagination } from "../ui/controls";
import { fieldError } from "../ui/fieldError";
import { dateTime } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import Switch from "../ui/Switch";
import ui from "../ui/ui.module.css";
import { ConversationRow } from "./Messages";
import styles from "./profile.module.css";

export default function Profile() {
  const { user, api, signOut, lang, t } = useSession();
  const navigate = useNavigate();
  const account = useRemote<User>("/me/profile");
  const settings = useRemote<NotificationSettings>("/me/notification-settings");
  const [chatPage, setChatPage] = useState(0);
  const [reportPage, setReportPage] = useState(0);
  const chats = useRemote<Page<Conversation>>(
    "/conversations?size=8&page=" + chatPage,
  );
  const reports = useRemote<Page<LostReport>>(
    "/lost-reports?status=RESOLVED&size=8&page=" + reportPage,
  );
  const [logout, setLogout] = useState(false);
  const action = useAction();
  const profile = account.data ?? user;

  return (
    <div className={ui.formPage + " " + styles.profilePage}>
      <SectionTitle title={t("마이페이지", "My profile")} back="/" />
      <section className={ui.panel + " " + styles.profileCard}>
        {profile && (
          <>
            <div className={styles.identity}>
              <UserRound size={32} strokeWidth={1.65} aria-hidden="true" />
              <h2>{profile.name}</h2>
            </div>
            <p className={styles.profileAffiliation}>
              {
                {
                  STUDENT: t("학생", "Student"),
                  FACULTY: t("교원", "Faculty"),
                  STAFF: t("직원", "Staff"),
                }[profile.affiliation]
              }
            </p>
          </>
        )}
        {account.error !== undefined && (
          <ErrorState error={account.error} retry={account.reload} />
        )}
        {settings.error !== undefined && (
          <ErrorState error={settings.error} retry={settings.reload} />
        )}
        {settings.data && (
          <Switch
            label={t("매칭 이메일 알림", "Match emails")}
            checked={settings.data.matchEmail}
            disabled={!settings.data.emailEnabled || action.busy}
            onChange={(checked) => {
              const previous = settings.data;
              if (!previous) return;
              void action.run(async () => {
                await api.request("/me/notification-settings", {
                  method: "PUT",
                  body: { ...previous, matchEmail: checked },
                });
                settings.reload();
              });
            }}
          />
        )}
        {action.error !== undefined && !logout && (
          <ErrorState error={action.error} />
        )}
        <div className={styles.accountActions}>
          {profile?.role === "ADMIN" && (
            <Link to="/admin">{t("관리자 페이지", "Admin dashboard")}</Link>
          )}
          <button
            type="button"
            className={styles.signOut}
            onClick={() => {
              action.clear();
              setLogout(true);
            }}
          >
            {t("로그아웃", "Sign out")}
          </button>
        </div>
      </section>
      <section className={ui.panel + " " + styles.profileCard}>
        <div className={ui.between}>
          <h2>{t("채팅방", "Conversations")}</h2>
          {chats.data && (
            <small className={styles.count}>
              {chats.data.totalElements}
              {t("개", " chats")}
            </small>
          )}
        </div>
        {chats.loading && <Loading />}
        {chats.error !== undefined && (
          <ErrorState error={chats.error} retry={chats.reload} />
        )}
        {chats.data?.items.length === 0 && (
          <p className={styles.profileAffiliation}>
            {t("아직 대화가 없어요.", "No conversations yet.")}
          </p>
        )}
        {chats.data?.items.length ? (
          <div className={styles.profileRows}>
            {chats.data.items.map((conversation) => (
              <ConversationRow
                conversation={conversation}
                key={conversation.conversationId}
                compact
              />
            ))}
          </div>
        ) : null}
        {chats.data && (
          <Pagination
            page={chatPage}
            total={chats.data.totalPages}
            change={setChatPage}
          />
        )}
      </section>
      <section className={ui.panel + " " + styles.profileCard}>
        <div className={ui.between}>
          <h2>{t("완료한 신고 내역", "Resolved reports")}</h2>
          {reports.data && (
            <small className={styles.count}>
              {reports.data.totalElements}
              {t("건", " reports")}
            </small>
          )}
        </div>
        {reports.loading && <Loading />}
        {reports.error !== undefined && (
          <ErrorState error={reports.error} retry={reports.reload} />
        )}
        {reports.data?.items.length === 0 && (
          <p className={styles.profileAffiliation}>
            {t("완료한 신고가 없어요.", "No resolved reports yet.")}
          </p>
        )}
        {reports.data?.items.length ? (
          <div className={styles.profileRows}>
            {reports.data.items.map((report) => (
              <Link
                className={styles.resolved}
                key={report.reportId}
                to={"/lost-reports/" + report.reportId}
              >
                <div>
                  <strong className={ui.userText}>{report.description}</strong>
                  {report.closedAt && (
                    <small className={styles.count}>
                      {t("완료일", "Resolved on")}{" "}
                      {dateTime(report.closedAt, lang)}
                    </small>
                  )}
                </div>
                <span className={ui.badge} data-status="COLLECTED">
                  {t("해결 완료", "Resolved")}
                </span>
              </Link>
            ))}
          </div>
        ) : null}
        {reports.data && (
          <Pagination
            page={reportPage}
            total={reports.data.totalPages}
            change={setReportPage}
          />
        )}
      </section>
      {logout && (
        <Dialog
          title={t("로그아웃할까요?", "Sign out?")}
          close={() => {
            if (!action.busy) setLogout(false);
          }}
        >
          <div className={ui.stack}>
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              type="button"
              className={ui.primary}
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await signOut();
                  navigate("/", { replace: true });
                })
              }
            >
              {t("로그아웃", "Sign out")}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function EmailForm({
  initial,
  reload,
}: {
  initial: NotificationSettings;
  reload: () => void;
}) {
  const { t, api } = useSession();
  const [draft, setDraft] = useState(initial);
  const [saved, setSaved] = useState(false);
  const action = useAction();
  const options: [keyof NotificationSettings, string][] = [
    ["emailEnabled", t("이메일 알림 받기", "Receive emails")],
    ["matchEmail", t("새 매칭 후보", "New match candidates")],
    ["collectionEmail", t("수거 알림", "Collection updates")],
    ["expiryEmail", t("습득물 만료", "Item expiry")],
    ["keywordEmail", t("키워드 일치", "Keyword matches")],
  ];
  return (
    <form
      className={ui.panel + " " + ui.stack}
      onSubmit={(event) => {
        event.preventDefault();
        void action.run(async () => {
          const value = await api.request<NotificationSettings>(
            "/me/notification-settings",
            { method: "PUT", body: draft },
          );
          setDraft(value);
          setSaved(true);
          reload();
        });
      }}
    >
      {options.map(([key, label]) => (
        <Switch
          key={key}
          label={label}
          checked={draft[key]}
          disabled={
            action.busy || (key !== "emailEnabled" && !draft.emailEnabled)
          }
          onChange={(checked) => {
            setDraft({ ...draft, [key]: checked });
            setSaved(false);
          }}
        />
      ))}
      {action.error !== undefined && <ErrorState error={action.error} />}
      {saved && (
        <p className={ui.notice} role="status">
          {t("설정을 저장했어요.", "Settings saved.")}
        </p>
      )}
      <button className={ui.primary} type="submit" disabled={action.busy}>
        {t("설정 저장", "Save settings")}
      </button>
    </form>
  );
}

export function EmailSettings() {
  const { t } = useSession();
  const settings = useRemote<NotificationSettings>("/me/notification-settings");
  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={t("이메일 알림 설정", "Email notification settings")}
        back="/me"
      />
      {settings.loading && <Loading />}
      {settings.error !== undefined && (
        <ErrorState error={settings.error} retry={settings.reload} />
      )}
      {settings.data && (
        <EmailForm initial={settings.data} reload={settings.reload} />
      )}
    </div>
  );
}

export function Keywords() {
  const { t, api } = useSession();
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(0);
  const [removing, setRemoving] = useState<Subscription>();
  const subscription = useRemote<Page<Subscription>>(
    "/me/keyword-subscriptions?page=" + page,
  );
  const action = useAction();

  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={t("키워드 구독", "Keyword subscriptions")}
        back="/me"
      />
      <form
        className={ui.panel + " " + ui.stack}
        onSubmit={(event) => {
          event.preventDefault();
          void action.run(async () => {
            await api.request("/me/keyword-subscriptions", {
              method: "POST",
              body: { keyword: keyword.trim() },
            });
            setKeyword("");
            setPage(0);
            subscription.reload();
          });
        }}
      >
        <label className={ui.field}>
          {t("새 키워드", "New keyword")}
          <input
            value={keyword}
            maxLength={100}
            required
            onChange={(event) => setKeyword(event.target.value)}
          />
          {fieldError(action.error, "keyword") && (
            <span className={ui.fieldError}>
              {fieldError(action.error, "keyword")}
            </span>
          )}
        </label>
        {!removing && action.error !== undefined && (
          <ErrorState error={action.error} />
        )}
        <button
          type="submit"
          className={ui.primary}
          disabled={action.busy || !keyword.trim()}
        >
          {t("구독 추가", "Add subscription")}
        </button>
      </form>
      {subscription.loading && <Loading />}
      {subscription.error !== undefined && (
        <ErrorState error={subscription.error} retry={subscription.reload} />
      )}
      {subscription.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("구독한 키워드가 없어요.", "No keyword subscriptions yet.")}
        </p>
      )}
      {subscription.data?.items.map((value) => (
        <div key={value.subscriptionId} className={ui.panel + " " + ui.between}>
          <strong className={ui.userText}>{value.keyword}</strong>
          <button
            type="button"
            className={ui.secondary}
            onClick={() => {
              action.clear();
              setRemoving(value);
            }}
          >
            {t("구독 해제", "Unsubscribe")}
          </button>
        </div>
      ))}
      {subscription.data && (
        <Pagination
          page={page}
          total={subscription.data.totalPages}
          change={setPage}
        />
      )}
      {removing && (
        <Dialog
          title={t(
            "키워드 구독을 해제할까요?",
            "Unsubscribe from this keyword?",
          )}
          close={() => {
            if (!action.busy) setRemoving(undefined);
          }}
        >
          <div className={ui.stack}>
            <p className={ui.userText}>{removing.keyword}</p>
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              type="button"
              className={ui.danger}
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await api.request(
                    "/me/keyword-subscriptions/" + removing.subscriptionId,
                    { method: "DELETE" },
                  );
                  if (page > 0 && subscription.data?.items.length === 1)
                    setPage(page - 1);
                  subscription.reload();
                  setRemoving(undefined);
                })
              }
            >
              {t("구독 해제", "Unsubscribe")}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
