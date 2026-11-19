import { PackageSearch } from "lucide-react";
import { useState } from "react";
import { useSession } from "../api/session-context";
import type { DropOff, ItemDetail, ItemSummary, Page } from "../api/types";
import { useRemote } from "../api/useRemote";
import { ErrorState, Loading, Pagination } from "../ui/controls";
import { dateTime, statusLabel } from "../ui/format";
import {
  EmptyReportList,
  ReportEntry,
  ReportGroup,
  ReportList,
} from "../ui/ReportList";
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
    <ReportEntry
      title={item.title}
      status={statusLabel(item.status, t)}
      to={path}
    >
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
    </ReportEntry>
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
    <ReportList
      title={t("습득 신고", "Found reports")}
      createTo="/found-items/new"
      createLabel={t("새 습득 신고하기", "New found report")}
    >
      {items.loading && <Loading />}
      {items.error !== undefined && (
        <ErrorState error={items.error} retry={items.reload} />
      )}
      {items.data?.items.length === 0 && (
        <EmptyReportList
          Icon={PackageSearch}
          title={t("습득 신고가 없어요", "No found reports yet")}
          description={t(
            "습득한 물품을 등록하고 주인을 찾아 주세요.",
            "Report a found item to help its owner find it.",
          )}
        />
      )}
      {active.length > 0 && (
        <ReportGroup
          title={t("진행 중인 습득 신고", "Active found reports")}
          count={activeCount.data?.totalElements ?? active.length}
        >
          {active.map((item) => (
            <FoundReport key={item.itemId} item={item} />
          ))}
        </ReportGroup>
      )}
      {previous.length > 0 && (
        <ReportGroup title={t("이전 습득 신고", "Previous found reports")}>
          {previous.map((item) => (
            <FoundReport key={item.itemId} item={item} />
          ))}
        </ReportGroup>
      )}
      {items.data && (
        <Pagination
          page={page}
          total={items.data.totalPages}
          change={setPage}
        />
      )}
    </ReportList>
  );
}
