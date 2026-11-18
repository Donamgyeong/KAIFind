import { SlidersHorizontal, Search } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type {
  Building,
  Category,
  ItemStatus,
  ItemSummary,
  Page,
} from "../api/types";
import { useRemote } from "../api/useRemote";
import {
  BuildingPicker,
  ErrorState,
  Loading,
  Pagination,
  Status,
} from "../ui/controls";
import { dateTime, itemStatuses, localName, statusLabel } from "../ui/format";
import PhotoView from "../ui/PhotoView";
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

export default function Home() {
  const { t, lang } = useSession();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const q = params.get("q") ?? "";
  const [search, setSearch] = useState(q);
  const [previousQuery, setPreviousQuery] = useState(q);
  if (q !== previousQuery) {
    setPreviousQuery(q);
    setSearch(q);
  }
  const buildings = useRemote<{ items: Building[] }>("/buildings", true);
  const categories = useRemote<{ items: Category[] }>("/categories", true);
  const preferredOrder = ["전자기기", "카드·지갑", "생활용품", "의류", "기타"];
  const priority = (category: Category) => {
    const index = preferredOrder.indexOf(category.nameKo);
    return index === -1 ? preferredOrder.length : index;
  };
  const choices = [...(categories.data?.items ?? [])].sort(
    (a, b) => priority(a) - priority(b),
  );
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
          <Search size={22} />
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
        <div className={styles.chips} aria-label={t("카테고리", "Categories")}>
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
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <span>
            {t("건물", "Building")} ▾ {t("날짜", "Date")} ▾{" "}
            {statuses.length === 1
              ? statusLabel(statuses[0], t)
              : t("상태", "Status")}{" "}
            ▾
          </span>
          <SlidersHorizontal size={18} />
        </button>
      </div>
      {categories.error !== undefined && (
        <ErrorState error={categories.error} retry={categories.reload} />
      )}
      {open && (
        <section
          className={ui.panel + " " + styles.filterPanel}
          aria-label={t("상세 검색 필터", "Advanced filters")}
        >
          <BuildingPicker
            label={t("발견 건물 선택", "Select found building")}
            buildings={buildings.data?.items ?? []}
            values={
              params.get("foundBuildingId")
                ? [params.get("foundBuildingId")!]
                : []
            }
            onChange={([id]) => update({ foundBuildingId: id ?? "" })}
          />
          {buildings.error !== undefined && (
            <ErrorState error={buildings.error} retry={buildings.reload} />
          )}
          <label>
            {t("발견일 시작", "Date from")}
            <input
              type="date"
              value={params.get("foundDateFrom") ?? ""}
              max={params.get("foundDateTo") ?? undefined}
              onChange={(event) =>
                update({ foundDateFrom: event.target.value })
              }
            />
          </label>
          <label>
            {t("발견일 종료", "Date to")}
            <input
              type="date"
              value={params.get("foundDateTo") ?? ""}
              min={params.get("foundDateFrom") ?? undefined}
              onChange={(event) => update({ foundDateTo: event.target.value })}
            />
          </label>
          <div className={ui.row}>
            {itemStatuses.map((status) => (
              <button
                key={status}
                type="button"
                className={ui.chip}
                aria-pressed={(statuses.length
                  ? statuses
                  : ["POSTED"]
                ).includes(status)}
                onClick={() => {
                  const active = statuses.length ? statuses : ["POSTED"];
                  update({
                    statuses: active.includes(status)
                      ? active.filter((value) => value !== status)
                      : [...active, status],
                  });
                }}
              >
                {statusLabel(status, t)}
              </button>
            ))}
            <button
              type="button"
              className={ui.textButton}
              onClick={() =>
                update({
                  foundBuildingId: "",
                  foundDateFrom: "",
                  foundDateTo: "",
                  statuses: [],
                })
              }
            >
              {t("필터 초기화", "Reset")}
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
      <Link className={styles.buildingLink} to="/buildings">
        {t("건물별 보관 물품", "Items by storage building")}
      </Link>
    </div>
  );
}
