import { Bell, Check, Clock3, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { Notification, Page } from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { Dialog, ErrorState, Loading, Pagination } from "../ui/controls";
import { dateTime } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";
import styles from "./profile.module.css";

function safeTarget(notification: Notification) {
  const path = notification.targetPath;
  if (path === "/found-items" || path === "/lost-reports") return path;
  if (notification.itemId && path === "/found-items/" + notification.itemId)
    return path;
  if (
    notification.reportId &&
    path === "/lost-reports/" + notification.reportId + "/matches"
  )
    return path;
  return "/me";
}

function NotificationList({ onNavigate }: { onNavigate?: () => void }) {
  const { api, t, lang } = useSession();
  const navigate = useNavigate();
  const [page, setPage] = useState(0);
  const query = useRemote<Page<Notification>>("/me/notifications?page=" + page);
  const action = useAction();
  const labels = {
    MATCH_CANDIDATE: { Icon: Search, label: t("매칭 알림", "Match alert") },
    ITEM_COLLECTED: { Icon: Check, label: t("수령 완료", "Item collected") },
    ITEM_EXPIRED: { Icon: Clock3, label: t("물품 만료", "Item expired") },
    KEYWORD_MATCH: { Icon: Bell, label: t("키워드 알림", "Keyword alert") },
  };

  async function open(notification: Notification) {
    await action.run(async () => {
      if (!notification.readAt) {
        await api.request("/me/notifications/" + notification.notificationId, {
          method: "PATCH",
          body: { read: true },
        });
      }
      onNavigate?.();
      navigate(safeTarget(notification));
    });
  }

  return (
    <div className={ui.stack}>
      {query.loading && <Loading />}
      {query.error !== undefined && (
        <ErrorState error={query.error} retry={query.reload} />
      )}
      {action.error !== undefined && <ErrorState error={action.error} />}
      {query.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("표시할 알림이 없어요.", "No notifications to show.")}
        </p>
      )}
      {query.data?.items.length ? (
        <ul className={styles.notificationList}>
          {query.data.items.map((notification) => {
            const { Icon, label } = labels[notification.type];
            return (
              <li key={notification.notificationId}>
                <button
                  type="button"
                  className={styles.notification}
                  data-unread={!notification.readAt}
                  disabled={action.busy}
                  onClick={() => void open(notification)}
                >
                  <span className={styles.notificationMeta}>
                    <Icon size={22} strokeWidth={1.65} aria-hidden="true" />
                    <span>{label}</span>
                    <time dateTime={notification.createdAt}>
                      {dateTime(notification.createdAt, lang)}
                    </time>
                    {!notification.readAt && (
                      <span
                        className={styles.unreadDot}
                        role="img"
                        aria-label={t("읽지 않음", "Unread")}
                      />
                    )}
                  </span>
                  <strong>{notification.message}</strong>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {query.data && (
        <Pagination
          page={page}
          total={query.data.totalPages}
          change={setPage}
        />
      )}
    </div>
  );
}

export default function Notifications() {
  const { t } = useSession();
  return (
    <div className={ui.formPage}>
      <SectionTitle title={t("알림", "Notifications")} back="/me" />
      <section className={ui.panel}>
        <NotificationList />
      </section>
    </div>
  );
}

export function NotificationPopup({ close }: { close: () => void }) {
  const { t } = useSession();
  return (
    <Dialog
      title={t("알림", "Notifications")}
      className={styles.notificationDialog}
      close={close}
    >
      <NotificationList onNavigate={close} />
    </Dialog>
  );
}
