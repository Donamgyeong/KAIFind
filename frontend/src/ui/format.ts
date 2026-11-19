import type { Building, Category, ItemStatus, Language } from "../api/types";
import type { Translate } from "../api/session-context";

export const itemStatuses: ItemStatus[] = ["POSTED", "COLLECTED", "EXPIRED"];

export function statusLabel(status: ItemStatus, t: Translate) {
  return {
    POSTED: t("게시 중", "Posted"),
    COLLECTED: t("수거 완료", "Collected"),
    EXPIRED: t("만료", "Expired"),
  }[status];
}

export function localName(value: Building | Category, lang: Language) {
  return lang === "ko" ? value.nameKo : value.nameEn;
}

export function orderCategories(categories: Category[]) {
  const order = ["전자기기", "카드·지갑", "생활용품", "의류", "기타"];
  const priority = ({ nameKo }: Category) => {
    const index = order.indexOf(nameKo);
    return index === -1 ? order.length : index;
  };
  return [...categories].sort((a, b) => priority(a) - priority(b));
}

export function dateTime(value: string, lang: Language) {
  return new Intl.DateTimeFormat(lang === "ko" ? "ko-KR" : "en-GB", {
    timeZone: "Asia/Seoul",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

export function kstInputValue(value = new Date().toISOString()) {
  return new Date(new Date(value).getTime() + 9 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 16);
}

export function timeOfDay(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

export function buildingZones(buildings: Building[], t: Translate) {
  const groups = [
    { code: "E", name: t("동측 구역", "East Zone") },
    { code: "W", name: t("서측 구역", "West Zone") },
    { code: "N", name: t("북측 구역", "North Zone") },
    { code: "", name: t("기타 건물", "Other buildings") },
  ];
  return groups
    .map(({ code, name }) => ({
      code,
      name,
      entries: buildings
        .filter(
          (building) =>
            building.active &&
            (building.code.match(/^([EWN])\d/i)?.[1]?.toUpperCase() ?? "") ===
              code,
        )
        .sort((a, b) => a.code.localeCompare(b.code, "en", { numeric: true })),
    }))
    .filter(({ entries }) => entries.length > 0);
}
