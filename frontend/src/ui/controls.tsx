import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { ApiError } from "../api/client";
import { useSession } from "../api/session-context";
import type { Building, ItemStatus } from "../api/types";
import { localName, statusLabel } from "./format";
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
}: {
  title: string;
  close: () => void;
  children: ReactNode;
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
      className={styles.dialog}
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
        <h2 id={id}>{title}</h2>
        <button
          className={styles.iconButton}
          type="button"
          aria-label={t("닫기", "Close")}
          onClick={close}
        >
          <X size={21} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function BuildingPicker({
  buildings,
  values,
  onChange,
  label,
  multiple = false,
  disabled = false,
}: {
  buildings: Building[];
  values: string[];
  onChange: (ids: string[]) => void;
  label: string;
  multiple?: boolean;
  disabled?: boolean;
}) {
  const { t, lang } = useSession();
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  const zones = [
    { code: "E", name: t("동측 구역", "East Zone") },
    { code: "W", name: t("서측 구역", "West Zone") },
    { code: "N", name: t("북측 구역", "North Zone") },
    { code: "", name: t("기타 건물", "Other buildings") },
  ];
  const group = (code: string) =>
    buildings
      .filter(
        (building) =>
          building.active &&
          (building.code.match(/^([EWN])\d/i)?.[1]?.toUpperCase() ?? "") ===
            code,
      )
      .sort((a, b) => a.code.localeCompare(b.code, "en", { numeric: true }));
  const selected = values.map((value) =>
    buildings.find((building) => building.buildingId === value),
  );
  return (
    <>
      <button
        type="button"
        className={styles.selectButton}
        disabled={disabled}
        aria-haspopup="dialog"
        onClick={() => ref.current?.showModal()}
      >
        {selected
          .filter(Boolean)
          .map(
            (building) => building!.code + " · " + localName(building!, lang),
          )
          .join(", ") || label}
        <ChevronRight size={16} />
      </button>
      <dialog ref={ref} className={styles.dialog} aria-labelledby={id}>
        <div className={styles.dialogHeader}>
          <h2 id={id}>{label}</h2>
          <button
            type="button"
            className={styles.iconButton}
            aria-label={t("닫기", "Close")}
            onClick={() => ref.current?.close()}
          >
            <X size={20} />
          </button>
        </div>
        <div className={styles.zoneList}>
          {zones.map(({ code, name }) => {
            const entries = group(code);
            if (!entries.length) return null;
            return (
              <details name={id} key={code} className={styles.zone}>
                <summary>
                  {name}
                  {code ? " (" + code + ")" : ""}
                  <ChevronRight size={16} />
                  <small>{entries.length}</small>
                </summary>
                <div className={styles.buildingOptions}>
                  {entries.map((building) => {
                    const checked = values.includes(building.buildingId);
                    return (
                      <button
                        type="button"
                        aria-pressed={checked}
                        key={building.buildingId}
                        onClick={() => {
                          const next = multiple
                            ? checked
                              ? values.filter(
                                  (value) => value !== building.buildingId,
                                )
                              : [...values, building.buildingId]
                            : [building.buildingId];
                          onChange(next);
                          if (!multiple) ref.current?.close();
                        }}
                      >
                        <b>{building.code}</b> {localName(building, lang)}
                        {checked && " ✓"}
                      </button>
                    );
                  })}
                </div>
              </details>
            );
          })}
          {!buildings.some((building) => building.active) && (
            <p>
              {t("선택 가능한 건물이 없습니다.", "No buildings available.")}
            </p>
          )}
        </div>
        {multiple && (
          <button
            type="button"
            className={styles.primary}
            onClick={() => ref.current?.close()}
          >
            {t("선택 완료", "Done")}
          </button>
        )}
      </dialog>
    </>
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
