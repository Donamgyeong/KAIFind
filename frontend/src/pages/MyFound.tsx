import { PackageSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { DropOff, ItemDetail, ItemSummary, Page } from "../api/types";
import { useRemote } from "../api/useRemote";
import { ErrorState, Loading, Pagination } from "../ui/controls";
import { dateTime, statusLabel } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";

function FoundReport({ item }: { item: ItemSummary }) {
  const { t, lang } = useSession();
  const path = "/found-items/" + item.itemId;
  const active = item.status === "POSTED";
  const detail = useRemote<ItemDetail>(active ? path : null);
  const storage = useRemote<DropOff>(active ? path + "/drop-off" : null);
  const location =
    storage.data?.mode === "KEPT_BY_FINDER"
      ? t("직접 보관", "Kept by finder")
      : [storage.data?.building?.code, storage.data?.spotDescription]
          .filter(Boolean)
          .join(" ");
  return (
    <article>
      <span className={ui.reportStatus}>{statusLabel(item.status, t)}</span>
      <h3 className={ui.reportTitle}>{item.title}</h3>
      <div className={ui.reportMeta}>
        <p>
          {t("발견 장소", "Found at")} · {item.foundBuilding.code}
          {detail.data?.foundLocationDescription &&
            " " + detail.data.foundLocationDescription}
        </p>
        {location && (
          <p>
            {t("보관 장소", "Stored at")} · {location}
          </p>
        )}
      </div>
      <small className={ui.reportMeta}>
        {t("등록일", "Posted on")} · {dateTime(item.createdAt, lang)}
      </small>
      <Link className={ui.secondary + " " + ui.full} to={path}>
        {t("신고 관리하기", "Manage report")}
      </Link>
    </article>
  );
}

export default function MyFound() {
  const { t } = useSession();
  const [page, setPage] = useState(0);
  const items = useRemote<Page<ItemSummary>>("/me/found-items?page=" + page);
  const activeCount = useRemote<Page<ItemSummary>>(
    (items.data?.totalPages ?? 0) > 1
      ? "/me/found-items?statuses=POSTED&size=1"
      : null,
  );
  const active =
    items.data?.items.filter((item) => item.status === "POSTED") ?? [];
  const previous =
    items.data?.items.filter((item) => item.status !== "POSTED") ?? [];

  return (
    <div className={ui.formPage + " " + ui.reportPage}>
      <SectionTitle title={t("습득 신고", "Found reports")} />
      {items.loading && <Loading />}
      {items.error !== undefined && (
        <ErrorState error={items.error} retry={items.reload} />
      )}
      {items.data?.items.length === 0 && (
        <section className={ui.panel + " " + ui.emptyCard}>
          <PackageSearch size={34} strokeWidth={1.65} aria-hidden="true" />
          <h2>{t("습득 신고가 없어요", "No found reports yet")}</h2>
          <p>
            {t(
              "습득한 물품을 등록하고 주인을 찾아 주세요.",
              "Report a found item to help its owner find it.",
            )}
          </p>
        </section>
      )}
      {active.length > 0 && (
        <section className={ui.panel + " " + ui.reportGroup}>
          <div className={ui.between}>
            <h2>{t("진행 중인 습득 신고", "Active found reports")}</h2>
            <span className={ui.reportCount}>
              {activeCount.data?.totalElements ?? active.length}
              {t("건", " reports")}
            </span>
          </div>
          {active.map((item) => (
            <FoundReport key={item.itemId} item={item} />
          ))}
        </section>
      )}
      {previous.length > 0 && (
        <section className={ui.panel + " " + ui.reportGroup}>
          <h2>{t("이전 습득 신고", "Previous found reports")}</h2>
          {previous.map((item) => (
            <FoundReport key={item.itemId} item={item} />
          ))}
        </section>
      )}
      {items.data && (
        <Pagination
          page={page}
          total={items.data.totalPages}
          change={setPage}
        />
      )}
      <div className={ui.reportFooter}>
        <Link className={ui.primary + " " + ui.full} to="/found-items/new">
          {t("새 습득 신고하기", "New found report")}
        </Link>
      </div>
    </div>
  );
}
