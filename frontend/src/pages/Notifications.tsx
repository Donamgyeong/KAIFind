import { ArrowUpRight, Bell, Check } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
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
  const [unread, setUnread] = useState(false);
  const [page, setPage] = useState(0);
  const query = useRemote<Page<Notification>>(
    "/me/notifications?page=" + page + "&unreadOnly=" + unread,
  );
  const action = useAction();

  async function mark(notification: Notification, open: boolean) {
    await action.run(async () => {
      if (!notification.readAt) {
        await api.request("/me/notifications/" + notification.notificationId, {
          method: "PATCH",
          body: { read: true },
        });
        query.reload();
      }
      if (open) {
        onNavigate?.();
        navigate(safeTarget(notification));
      }
    });
  }

  return (
    <div className={ui.stack}>
      <div className={ui.between}>
        <label className={ui.row}>
          <input
            type="checkbox"
            checked={unread}
            onChange={(event) => {
              setUnread(event.target.checked);
              setPage(0);
            }}
          />
          {t("안 읽은 알림만", "Unread only")}
        </label>
        <button className={ui.textButton} type="button" onClick={query.reload}>
          {t("새로고침", "Refresh")}
        </button>
      </div>
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
      <ul className={styles.notificationList}>
        {query.data?.items.map((notification) => (
          <li
            key={notification.notificationId}
            data-unread={!notification.readAt}
          >
            <button
              type="button"
              className={styles.notification}
              disabled={action.busy}
              onClick={() => void mark(notification, true)}
            >
              <Bell size={18} aria-hidden="true" />
              <span>
                <strong>{notification.message}</strong>
                <time dateTime={notification.createdAt}>
                  {dateTime(notification.createdAt, lang)} KST
                </time>
              </span>
              <ArrowUpRight size={16} aria-hidden="true" />
            </button>
            {!notification.readAt && (
              <button
                type="button"
                disabled={action.busy}
                className={ui.iconButton}
                aria-label={t("읽음 처리", "Mark as read")}
                onClick={() => void mark(notification, false)}
              >
                <Check size={18} />
              </button>
            )}
          </li>
        ))}
      </ul>
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
    <Dialog title={t("알림", "Notifications")} close={close}>
      <NotificationList onNavigate={close} />
      <Link
        className={ui.secondary + " " + ui.full}
        to="/me/notifications"
        onClick={close}
      >
        {t("전체 알림 보기", "View all notifications")}
      </Link>
    </Dialog>
  );
}
