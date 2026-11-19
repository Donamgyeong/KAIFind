import { useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useSession } from "../api/session-context";
import { Dialog } from "./controls";
import { kstInputValue } from "./format";
import PickerButton from "./PickerButton";
import ui from "./ui.module.css";
import styles from "./date-field.module.css";

function monthStart(value: string) {
  return new Date(value.slice(0, 7) + "-01T00:00:00Z");
}

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function validDay(value = "") {
  const day = value.slice(0, 10);
  if (!/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(day)) return "";
  const parsed = new Date(day + "T00:00:00Z");
  return Number.isFinite(parsed.getTime()) && isoDate(parsed) === day
    ? day
    : "";
}

function moveMonth(month: Date, steps: number) {
  const next = new Date(month);
  next.setUTCMonth(next.getUTCMonth() + steps);
  return next;
}

function Calendar({
  title,
  initial,
  time,
  min,
  max,
  close,
  save,
}: {
  title: string;
  initial: string;
  time: boolean;
  min?: string;
  max?: string;
  close: () => void;
  save: (value: string) => void;
}) {
  const { lang, t } = useSession();
  const today = kstInputValue().slice(0, 10);
  const lower = validDay(min);
  const upper = validDay(max);
  const candidate = validDay(initial) || today;
  const startingDate =
    lower && candidate < lower
      ? lower
      : upper && candidate > upper
        ? upper
        : candidate;
  const [day, setDay] = useState(startingDate);
  const [month, setMonth] = useState(() => monthStart(startingDate));
  const [hour, setHour] = useState(initial.slice(11, 13) || "12");
  const [minute, setMinute] = useState(initial.slice(14, 16) || "00");
  const locale = lang === "ko" ? "ko-KR" : "en-US";
  const monthTitle = new Intl.DateTimeFormat(locale, {
    timeZone: "UTC",
    year: "numeric",
    month: "long",
  }).format(month);
  const weekdays = new Intl.DateTimeFormat(locale, {
    timeZone: "UTC",
    weekday: lang === "ko" ? "short" : "narrow",
  });
  const fullDay = new Intl.DateTimeFormat(locale, {
    timeZone: "UTC",
    dateStyle: "full",
  });
  const nextMonth = moveMonth(month, 1);
  const prevMonth = moveMonth(month, -1);
  const firstDay = month.getUTCDay();
  const lastDay = new Date(nextMonth);
  lastDay.setUTCDate(0);
  const daysInMonth = lastDay.getUTCDate();
  const selected = time ? day + "T" + hour + ":" + minute : day;
  const valid =
    (!min || !lower || selected >= min) && (!max || !upper || selected <= max);
  const dayValues = Array.from({ length: daysInMonth }, (_, index) => {
    const current = new Date(month);
    current.setUTCDate(index + 1);
    return current;
  });

  return (
    <Dialog title={title} close={close} className={styles.picker}>
      <div className={styles.month}>
        <button
          type="button"
          className={ui.iconButton}
          aria-label={t("이전 달", "Previous month")}
          disabled={month <= monthStart(lower || "0001-01-01")}
          onClick={() => setMonth(prevMonth)}
        >
          <ChevronLeft size={20} strokeWidth={1.65} />
        </button>
        <strong aria-live="polite">{monthTitle}</strong>
        <button
          type="button"
          className={ui.iconButton}
          aria-label={t("다음 달", "Next month")}
          disabled={
            nextMonth.getUTCFullYear() > 9999 ||
            (!!upper && isoDate(nextMonth) > upper)
          }
          onClick={() => setMonth(nextMonth)}
        >
          <ChevronRight size={20} strokeWidth={1.65} />
        </button>
      </div>
      <div className={styles.calendar}>
        {Array.from({ length: 7 }, (_, index) => (
          <span key={"weekday-" + index}>
            {weekdays.format(new Date(Date.UTC(2024, 0, 7 + index)))}
          </span>
        ))}
        {Array.from({ length: firstDay }, (_, index) => (
          <span key={"blank-" + index} aria-hidden="true" />
        ))}
        {dayValues.map((date) => {
          const value = isoDate(date);
          return (
            <button
              type="button"
              key={value}
              aria-label={fullDay.format(date)}
              aria-pressed={value === day}
              disabled={
                (!!lower && value < lower) || (!!upper && value > upper)
              }
              onClick={() => setDay(value)}
            >
              {date.getUTCDate()}
            </button>
          );
        })}
      </div>
      {time && (
        <div className={styles.times}>
          <label className={ui.field}>
            {t("시", "Hour")}
            <select
              value={hour}
              onChange={(event) => setHour(event.target.value)}
            >
              {Array.from({ length: 24 }, (_, i) =>
                String(i).padStart(2, "0"),
              ).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className={ui.field}>
            {t("분", "Minute")}
            <select
              value={minute}
              onChange={(event) => setMinute(event.target.value)}
            >
              {Array.from({ length: 60 }, (_, i) =>
                String(i).padStart(2, "0"),
              ).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div className={styles.actions}>
        <span>
          {day.replaceAll("-", lang === "ko" ? "." : "-")}
          {time && " " + hour + ":" + minute + " KST"}
        </span>
        <button
          type="button"
          className={ui.primary}
          disabled={!valid}
          onClick={() => save(selected)}
        >
          {t("선택 완료", "Confirm date")}
        </button>
      </div>
    </Dialog>
  );
}

export default function DateField({
  label,
  value,
  onChange,
  name,
  min,
  max,
  time = false,
}: {
  label: string;
  value?: string;
  onChange?: (value: string) => void;
  name?: string;
  min?: string;
  max?: string;
  time?: boolean;
}) {
  const { lang, t } = useSession();
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const candidate = value ?? draft;
  const day = validDay(candidate);
  const selected = day ? candidate : "";
  const displayValue = day
    ? day.replaceAll("-", lang === "ko" ? "." : "-") +
      (time ? " " + selected.slice(11, 16) : "")
    : undefined;
  const placeholder = time
    ? t("날짜·시각 선택", "Select date & time")
    : t("날짜 선택", "Select date");
  return (
    <>
      {name && <input type="hidden" name={name} value={selected} />}
      <PickerButton
        label={label}
        value={displayValue}
        placeholder={placeholder}
        open={open}
        onOpen={() => setOpen(true)}
        icon={CalendarDays}
      />
      {open && (
        <Calendar
          title={label}
          initial={selected}
          min={min}
          max={max}
          time={time}
          close={() => setOpen(false)}
          save={(result) => {
            if (value === undefined) setDraft(result);
            onChange?.(result);
            setOpen(false);
          }}
        />
      )}
    </>
  );
}
