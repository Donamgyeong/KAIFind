import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { ApiError } from "../api/client";
import { useSession } from "../api/session-context";
import type { ItemStatus } from "../api/types";
import { statusLabel } from "./format";
import styles from "./ui.module.css";

export function Status({ status }: { status: ItemStatus }) {
  const { t } = useSession();
  return (
    <span className={styles.badge} data-status={status}>
      {statusLabel(status, t)}
    </span>
  );
}

export function Loading() {
  const { t } = useSession();
  return (
    <p className={styles.feedback} role="status">
      {t("불러오는 중…", "Loading…")}
    </p>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const { t } = useSession();
  const message =
    error instanceof ApiError && error.message
      ? error.message
      : t(
          "연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
          "Could not connect. Please try again.",
        );
  return (
    <div className={styles.error} role="alert">
      {message}
      {retry && (
        <button type="button" className={styles.textButton} onClick={retry}>
          {t("다시 시도", "Retry")}
        </button>
      )}
    </div>
  );
}

export function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className={styles.field} aria-describedby={error ? id : undefined}>
      <div className={styles.fieldLabel}>{label}</div>
      {children}
      {error && (
        <p id={id} className={styles.fieldError} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function Dialog({
  title,
  close,
  children,
  className,
  back,
  closeButtonClassName,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
  className?: string;
  back?: () => void;
  closeButtonClassName?: string;
}) {
  const { t } = useSession();
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={[styles.dialog, className].filter(Boolean).join(" ")}
      aria-labelledby={id}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          const bounds = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
          )
            close();
        }
      }}
    >
      <div className={styles.dialogHeader}>
        {back && (
          <button
            type="button"
            className={styles.iconButton}
            aria-label={t("구역 다시 선택", "Choose another zone")}
            onClick={back}
          >
            <ChevronLeft size={24} strokeWidth={1.65} />
          </button>
        )}
        <h2 id={id}>{title}</h2>
        <button
          className={[styles.iconButton, closeButtonClassName]
            .filter(Boolean)
            .join(" ")}
          type="button"
          aria-label={t("닫기", "Close")}
          onClick={close}
        >
          <X size={20} strokeWidth={1.65} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function Pagination({
  page,
  total,
  change,
}: {
  page: number;
  total: number;
  change: (page: number) => void;
}) {
  const { t } = useSession();
  if (total <= 1) return null;
  return (
    <nav className={styles.pagination} aria-label={t("페이지", "Pages")}>
      <button
        type="button"
        className={styles.iconButton}
        disabled={!page}
        aria-label={t("이전 페이지", "Previous page")}
        onClick={() => change(page - 1)}
      >
        <ChevronLeft size={20} />
      </button>
      <span>
        {page + 1} / {total}
      </span>
      <button
        type="button"
        className={styles.iconButton}
        disabled={page + 1 >= total}
        aria-label={t("다음 페이지", "Next page")}
        onClick={() => change(page + 1)}
      >
        <ChevronRight size={20} />
      </button>
    </nav>
  );
}
