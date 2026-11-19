import { Search } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { ItemStatus, ItemSummary, Page } from "../api/types";
import { useBuildings, useCategories } from "../api/useReferences";
import { useRemote } from "../api/useRemote";
import filterIcon from "../assets/filter.svg";
import DateField from "../ui/DateField";
import { ErrorState, Loading, Pagination, Status } from "../ui/controls";
import {
  dateTime,
  itemStatuses,
  localName,
  orderCategories,
  statusLabel,
} from "../ui/format";
import PhotoView from "../ui/PhotoView";
import { BuildingPicker } from "../ui/ReferenceFields";
import ui from "../ui/ui.module.css";
import styles from "./home.module.css";

export function ItemCard({ item }: { item: ItemSummary }) {
  const { user, t, lang } = useSession();
  const locked = !user && item.sensitive && !item.photos.length;
  return (
    <Link to={"/found-items/" + item.itemId} className={styles.card}>
      <PhotoView
        className={styles.cardImage}
        photo={item.photos[0]}
        locked={locked}
      />
      <div className={styles.cardText}>
        <strong>{item.title}</strong>
        {locked ? (
          <p>{t("로그인 후 확인하세요", "Sign in to view photo")}</p>
        ) : (
          <div className={styles.cardMeta}>
            <span>
              {item.foundBuilding.code} · {dateTime(item.foundAt, lang)}
            </span>
            <Status status={item.status} />
          </div>
        )}
      </div>
    </Link>
  );
}

type FilterDraft = {
  building: string;
  from: string;
  to: string;
  status: ItemStatus | "ALL";
};

export default function Home() {
  const { t, lang } = useSession();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<FilterDraft>();
  const q = params.get("q") ?? "";
  const [search, setSearch] = useState(q);
  const [previousQuery, setPreviousQuery] = useState(q);
  if (q !== previousQuery) {
    setPreviousQuery(q);
    setSearch(q);
  }
  const buildings = useBuildings();
  const categories = useCategories();
  const choices = orderCategories(categories.data?.items ?? []);
  const request = new URLSearchParams();
  for (const field of [
    "q",
    "categoryId",
    "foundBuildingId",
    "foundDateFrom",
    "foundDateTo",
    "page",
  ]) {
    const value = params.get(field);
    if (value) request.set(field, value);
  }
  const statuses = params
    .getAll("statuses")
    .filter((value): value is ItemStatus =>
      itemStatuses.includes(value as ItemStatus),
    );
  statuses.forEach((status) => request.append("statuses", status));
  const current: FilterDraft = {
    building: params.get("foundBuildingId") ?? "",
    from: params.get("foundDateFrom") ?? "",
    to: params.get("foundDateTo") ?? "",
    status: statuses.length > 1 ? "ALL" : (statuses[0] ?? "POSTED"),
  };
  const reset: FilterDraft = {
    building: "",
    from: "",
    to: "",
    status: "POSTED",
  };
  const hasFilters =
    (filter ?? current).building ||
    (filter ?? current).from ||
    (filter ?? current).to ||
    (filter ?? current).status !== "POSTED";
  function apply(draft: FilterDraft) {
    update({
      foundBuildingId: draft.building,
      foundDateFrom: draft.from,
      foundDateTo: draft.to,
      statuses:
        draft.status === "ALL"
          ? itemStatuses
          : draft.status === "POSTED"
            ? []
            : [draft.status],
    });
  }

  const items = useRemote<Page<ItemSummary>>(
    "/found-items?" + request.toString(),
    true,
  );

  function update(changes: Record<string, string | string[]>) {
    const next = new URLSearchParams(params);
    next.delete("page");
    for (const [key, value] of Object.entries(changes)) {
      next.delete(key);
      for (const entry of typeof value === "string" ? [value] : value)
        if (entry) next.append(key, entry);
    }
    setParams(next);
  }

  return (
    <div className={styles.home}>
      <form
        className={styles.search}
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          update({ q: search.trim() });
        }}
      >
        <button type="submit" aria-label={t("검색", "Search")}>
          <Search size={22} strokeWidth={1.65} />
        </button>
        <input
          aria-label={t("키워드 검색", "Search by keyword")}
          placeholder={t(
            "어떤 물건을 찾고 있나요?",
            "What are you looking for?",
          )}
          type="search"
          value={search}
          maxLength={100}
          onChange={(event) => setSearch(event.target.value)}
        />
      </form>
      <div className={styles.filters}>
        <div
          className={styles.chips}
          role="group"
          aria-label={t("카테고리", "Categories")}
        >
          <button
            type="button"
            className={ui.chip}
            aria-pressed={!params.has("categoryId")}
            onClick={() => update({ categoryId: "" })}
          >
            {t("전체", "All")}
          </button>
          {choices.map((category) => (
            <button
              type="button"
              key={category.categoryId}
              className={ui.chip}
              aria-pressed={params.get("categoryId") === category.categoryId}
              onClick={() => update({ categoryId: category.categoryId })}
            >
              {localName(category, lang)}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={styles.filterToggle}
          aria-expanded={!!filter}
          aria-controls="found-filters"
          onClick={() => setFilter(filter ? undefined : current)}
        >
          <span>
            {t("건물", "Building")} ▾ {t("날짜", "Date")} ▾{" "}
            {current.status === "ALL"
              ? t("전체", "All")
              : statusLabel(current.status, t)}{" "}
            ▾
          </span>
          <img src={filterIcon} alt="" />
        </button>
      </div>
      {categories.error !== undefined && (
        <ErrorState error={categories.error} retry={categories.reload} />
      )}

      {filter && (
        <section
          id="found-filters"
          className={styles.filterPanel}
          aria-label={t("상세 검색 필터", "Advanced filters")}
        >
          <div className={styles.filterField}>
            <span>{t("발견 건물", "Found building")}</span>
            <BuildingPicker
              label={t("발견 건물 선택", "Select found building")}
              buildings={buildings.data?.items ?? []}
              values={filter.building ? [filter.building] : []}
              onChange={([building]) =>
                setFilter({ ...filter, building: building ?? "" })
              }
            />
            {buildings.error !== undefined && (
              <ErrorState error={buildings.error} retry={buildings.reload} />
            )}
          </div>
          <div className={styles.dateRange}>
            <div className={styles.filterField}>
              <span>{t("시작 날짜", "Date from")}</span>
              <DateField
                label={t("시작 날짜", "Date from")}
                value={filter.from}
                max={filter.to || undefined}
                onChange={(from) => setFilter({ ...filter, from })}
              />
            </div>
            <span aria-hidden="true">~</span>
            <div className={styles.filterField}>
              <span>{t("종료 날짜", "Date to")}</span>
              <DateField
                label={t("종료 날짜", "Date to")}
                value={filter.to}
                min={filter.from || undefined}
                onChange={(to) => setFilter({ ...filter, to })}
              />
            </div>
          </div>
          <div className={styles.filterField}>
            <span>{t("물품 상태", "Item status")}</span>
            <div
              className={styles.statusSwitch}
              role="group"
              aria-label={t("물품 상태", "Item status")}
            >
              {(["ALL", "POSTED", "COLLECTED"] as const).map((status) => (
                <button
                  type="button"
                  key={status}
                  aria-pressed={filter.status === status}
                  onClick={() => setFilter({ ...filter, status })}
                >
                  {status === "ALL"
                    ? t("전체", "All")
                    : status === "COLLECTED"
                      ? t("수령 완료", "Collected")
                      : statusLabel(status, t)}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.filterActions}>
            <button
              type="button"
              className={ui.secondary + " " + styles.reset}
              disabled={!hasFilters}
              onClick={() => {
                setFilter(reset);
                apply(reset);
              }}
            >
              {t("필터 초기화", "Reset filters")}
            </button>
            <button
              type="button"
              className={ui.primary}
              onClick={() => {
                apply(filter);
                setFilter(undefined);
              }}
            >
              {t("검색 적용하기", "Apply filters")}
            </button>
          </div>
        </section>
      )}

      <div className={ui.between}>
        <h1 className={styles.heading}>
          {t("최근 발견된 물건", "Recently found items")}
        </h1>
        {items.data && (
          <span className={styles.resultCount}>
            {t("최신순", "Newest")} · {items.data.totalElements}
            {t("개", " items")}
          </span>
        )}
      </div>
      {items.loading && <Loading />}

      {items.error !== undefined && (
        <ErrorState error={items.error} retry={items.reload} />
      )}
      {items.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("검색 조건에 맞는 물건이 없어요.", "No items match your search.")}
        </p>
      )}
      {items.data && (
        <>
          <div className={styles.grid}>
            {items.data.items.map((item) => (
              <ItemCard key={item.itemId} item={item} />
            ))}
          </div>
          <Pagination
            page={items.data.page}
            total={items.data.totalPages}
            change={(page) => update({ page: String(page) })}
          />
        </>
      )}
    </div>
  );
}
