import { Check, ChevronDown, ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import { useSession } from "../api/session-context";
import type { Building, Category } from "../api/types";
import { Dialog } from "./controls";
import { buildingZones, localName, orderCategories } from "./format";
import styles from "./reference-fields.module.css";
import ui from "./ui.module.css";

function PickerChoice({
  code,
  label,
  selected,
  forward,
  pick,
}: {
  code?: string;
  label: string;
  selected?: boolean;
  forward?: boolean;
  pick: () => void;
}) {
  return (
    <button
      type="button"
      className={styles.choice}
      aria-pressed={selected}
      onClick={pick}
    >
      {code && <b>{code}</b>}
      <span>{label}</span>
      {forward && (
        <ChevronRight size={24} strokeWidth={1.65} aria-hidden="true" />
      )}
      {selected && <Check size={20} strokeWidth={1.65} aria-hidden="true" />}
    </button>
  );
}

export function CategorySelect({
  categories,
  value,
  change,
  label,
}: {
  categories: Category[];
  value: string;
  change: (value: string) => void;
  label: string;
}) {
  const { t, lang } = useSession();
  const [open, setOpen] = useState(false);
  const selectionId = useId();
  const selected = categories.find((category) => category.categoryId === value);
  return (
    <>
      <button
        type="button"
        className={ui.selectButton}
        aria-label={label}
        aria-describedby={selected ? selectionId : undefined}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-placeholder={!selected}
        onClick={() => setOpen(true)}
      >
        <span id={selectionId}>
          {selected
            ? localName(selected, lang)
            : t("물품 분류를 선택해 주세요", "Select a category")}
        </span>
        <ChevronDown size={16} strokeWidth={1.65} aria-hidden="true" />
      </button>
      {open && (
        <Dialog
          title={t("분류 선택", "Choose a category")}
          className={styles.sheet + " " + styles.categorySheet}
          closeButtonClassName={styles.close}
          close={() => setOpen(false)}
        >
          <div className={styles.options}>
            {orderCategories(categories).map((category) => (
              <PickerChoice
                key={category.categoryId}
                label={localName(category, lang)}
                selected={category.categoryId === value}
                pick={() => {
                  change(category.categoryId);
                  setOpen(false);
                }}
              />
            ))}
            {!categories.length && (
              <p>
                {t("선택 가능한 분류가 없습니다.", "No categories available.")}
              </p>
            )}
          </div>
        </Dialog>
      )}
    </>
  );
}

export function BuildingPicker({
  buildings,
  values,
  onChange,
  label,
  multiple = false,
}: {
  buildings: Building[];
  values: string[];
  onChange: (ids: string[]) => void;
  label: string;
  multiple?: boolean;
}) {
  const { t, lang } = useSession();
  const [open, setOpen] = useState(false);
  const [zoneCode, setZone] = useState<string>();
  const zones = buildingZones(buildings, t);
  const zone = zones.find(({ code }) => code === zoneCode);
  const selected = buildings.find((building) =>
    values.includes(building.buildingId),
  );
  const showSelection = !multiple && !!selected;
  return (
    <>
      <button
        type="button"
        className={ui.selectButton}
        data-placeholder={!showSelection}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          setZone(undefined);
          setOpen(true);
        }}
      >
        <span>
          {showSelection
            ? selected.code + " · " + localName(selected, lang)
            : label}
        </span>
        <ChevronDown size={16} strokeWidth={1.65} aria-hidden="true" />
      </button>
      {open && (
        <Dialog
          title={label}
          className={
            styles.sheet +
            " " +
            (zone ? styles.buildingSheet : styles.zoneSheet)
          }
          closeButtonClassName={styles.close}
          back={zone ? () => setZone(undefined) : undefined}
          close={() => setOpen(false)}
        >
          {zone ? (
            <div className={styles.options} key={zone.code}>
              {zone.entries.map((building) => {
                const id = building.buildingId;
                const checked = values.includes(id);
                return (
                  <PickerChoice
                    key={id}
                    code={building.code}
                    label={localName(building, lang)}
                    selected={checked}
                    pick={() => {
                      if (!multiple) {
                        onChange([id]);
                        setOpen(false);
                        return;
                      }
                      onChange(
                        checked
                          ? values.filter((value) => value !== id)
                          : [...values, id],
                      );
                    }}
                  />
                );
              })}
            </div>
          ) : (
            <div className={styles.options}>
              {zones.map(({ code, name }) => (
                <PickerChoice
                  key={code}
                  code={code}
                  label={name}
                  forward
                  pick={() => setZone(code)}
                />
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
              className={ui.secondary + " " + ui.full + " " + styles.done}
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
