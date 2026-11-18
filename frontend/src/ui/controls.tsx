import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { ApiError } from "../api/client";
import { useSession } from "../api/session-context";
import type { Building, ItemStatus } from "../api/types";
import { buildingZones, localName, statusLabel } from "./format";
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
  const [open, setOpen] = useState(false);
  const [zoneCode, setZone] = useState<string>();
  const zones = buildingZones(buildings, t);
  const zone = zones.find(({ code }) => code === zoneCode);
  const selected = buildings.filter((building) =>
    values.includes(building.buildingId),
  );
  const summary = multiple
    ? label
    : selected
        .map((building) => building.code + " · " + localName(building, lang))
        .join(", ") || label;
  return (
    <>
      <button
        type="button"
        className={styles.selectButton}
        disabled={disabled}
        aria-haspopup="dialog"
        onClick={() => {
          setZone(undefined);
          setOpen(true);
        }}
      >
        {summary}
        <ChevronRight size={16} />
      </button>
      {open && (
        <Dialog title={label} close={() => setOpen(false)}>
          {zone ? (
            <>
              <button
                type="button"
                className={styles.textButton}
                onClick={() => setZone(undefined)}
              >
                <ChevronLeft size={16} />{" "}
                {t("구역 다시 선택", "Choose another zone")}
              </button>
              <p className={styles.zoneHeading}>
                {zone.name} · {zone.entries.length}
                {t("개 건물", " buildings")}
              </p>
              <div className={styles.buildingOptions}>
                {zone.entries.map((building) => {
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
                        if (!multiple) setOpen(false);
                      }}
                    >
                      <b>{building.code}</b> {localName(building, lang)}
                      {checked && " ✓"}
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <div className={styles.zoneList}>
              {zones.map(({ code, name, entries }) => (
                <button
                  type="button"
                  className={styles.zoneChoice}
                  key={code}
                  onClick={() => setZone(code)}
                >
                  <span>
                    {name}
                    {code ? " (" + code + ")" : ""}
                    <small>
                      {entries.length}
                      {t("개 건물", " buildings")}
                    </small>
                  </span>
                  <ChevronRight size={16} />
                </button>
              ))}
              {!zones.length && (
                <p>
                  {t("선택 가능한 건물이 없습니다.", "No buildings available.")}
                </p>
              )}
            </div>
          )}
          {multiple && (
            <button
              type="button"
              className={styles.primary + " " + styles.full}
              onClick={() => setOpen(false)}
            >
              {t("선택 완료", "Done")}
            </button>
          )}
        </Dialog>
      )}
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
