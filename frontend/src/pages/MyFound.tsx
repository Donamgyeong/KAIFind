import { Plus, PackageSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { ItemStatus, ItemSummary, Page } from "../api/types";
import { useRemote } from "../api/useRemote";
import { ErrorState, Loading, Pagination } from "../ui/controls";
import { itemStatuses, statusLabel } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";
import { ItemCard } from "./Home";
import styles from "./home.module.css";

export default function MyFound() {
  const { t } = useSession();
  const [status, setStatus] = useState<ItemStatus | "">("");
  const [page, setPage] = useState(0);
  const items = useRemote<Page<ItemSummary>>(
    "/me/found-items?page=" + page + (status ? "&statuses=" + status : ""),
  );
  return (
    <div className={ui.stack}>
      <div className={ui.between}>
        <SectionTitle title={t("습득 신고", "Found items")} />
        <Link className={ui.primary} to="/found-items/new">
          <Plus size={19} />
          {t("습득물 등록", "Post found item")}
        </Link>
      </div>
      <div className={ui.row}>
        <button
          type="button"
          className={ui.chip}
          aria-pressed={!status}
          onClick={() => {
            setStatus("");
            setPage(0);
          }}
        >
          {t("전체", "All")}
        </button>
        {itemStatuses.map((value) => (
          <button
            key={value}
            type="button"
            className={ui.chip}
            aria-pressed={value === status}
            onClick={() => {
              setStatus(value);
              setPage(0);
            }}
          >
            {statusLabel(value, t)}
          </button>
        ))}
      </div>
      {items.loading && <Loading />}
      {items.error !== undefined && (
        <ErrorState error={items.error} retry={items.reload} />
      )}
      {items.data?.items.length === 0 && (
        <div className={ui.panel + " " + ui.emptyCard}>
          <PackageSearch size={34} aria-hidden="true" />
          <h2>{t("습득 신고가 없어요", "No found items here")}</h2>
          <p>
            {t(
              "습득한 물품을 등록하고 주인을 찾아 주세요.",
              "Post a found item to help its owner find it.",
            )}
          </p>
        </div>
      )}
      {items.data && (
        <>
          <div className={styles.grid}>
            {items.data.items.map((item) => (
              <ItemCard item={item} key={item.itemId} />
            ))}
          </div>
          <Pagination
            page={page}
            total={items.data.totalPages}
            change={setPage}
          />
        </>
      )}
    </div>
  );
}
