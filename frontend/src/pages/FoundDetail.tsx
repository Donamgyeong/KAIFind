import BuildingMap from "../ui/BuildingMap";
import { useState } from "react";
import { LockKeyhole } from "lucide-react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type {
  Building,
  DropOff,
  DropOffHistory,
  ItemDetail,
  Page,
} from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { signInPath } from "../routing";
import {
  Dialog,
  ErrorState,
  Loading,
  Pagination,
  Status,
} from "../ui/controls";
import { kstDateTime, localName } from "../ui/format";
import PhotoView from "../ui/PhotoView";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";
import styles from "./found.module.css";
import ItemInteractions from "./ItemInteractions";
import ReportItem from "./ReportItem";

function BuildingLocation({
  building,
  description,
}: {
  building: Building;
  description?: string | null;
}) {
  const { lang } = useSession();
  return (
    <div className={styles.location}>
      <strong>
        {building.code} · {localName(building, lang)}
      </strong>
      {description && <p>{description}</p>}
    </div>
  );
}

function LocationHistory({ path }: { path: string }) {
  const { t, lang } = useSession();
  const [page, setPage] = useState(0);
  const history = useRemote<Page<DropOffHistory>>(
    path + "/drop-off/history?page=" + page,
  );
  if (history.loading) return <Loading />;
  if (history.error !== undefined)
    return <ErrorState error={history.error} retry={history.reload} />;
  return (
    <>
      <ol className={styles.history}>
        {history.data?.items.map((entry) => (
          <li key={entry.historyId}>
            <time dateTime={entry.changedAt}>
              {kstDateTime(entry.changedAt, lang)}
            </time>
            <div>
              {entry.after.building
                ? entry.after.building.code +
                  " · " +
                  (entry.after.spotDescription ?? "")
                : t("직접 보관", "Kept by finder")}
            </div>
            {entry.before && (
              <small>
                {t("이전", "Previously")} ·{" "}
                {entry.before.building
                  ? entry.before.building.code +
                    " · " +
                    (entry.before.spotDescription ?? "")
                  : t("직접 보관", "Kept by finder")}
              </small>
            )}
          </li>
        ))}
      </ol>
      {history.data && (
        <Pagination
          page={page}
          total={history.data.totalPages}
          change={setPage}
        />
      )}
    </>
  );
}

function DetailContent({
  item,
  reload,
}: {
  item: ItemDetail;
  reload: () => void;
}) {
  const { user, t, lang, api, checking } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const path = "/found-items/" + item.itemId;
  const dropOff = useRemote<DropOff>(user ? path + "/drop-off" : null);
  const [history, showHistory] = useState(false);
  const [confirm, setConfirm] = useState<"delete" | "repost">();
  const action = useAction();
  const owner = user?.userId === item.finder.userId;

  return (
    <div className={styles.detail}>
      <SectionTitle title={t("물품 상세", "Item details")} back="/" />
      <div className={styles.layout}>
        <section className={ui.panel + " " + styles.overview}>
          <div
            className={styles.gallery}
            tabIndex={item.photos.length > 1 ? 0 : undefined}
            aria-label={t("물품 사진", "Item photos")}
          >
            {item.photos.length ? (
              item.photos.map((photo) => (
                <PhotoView
                  key={photo.photoId}
                  photo={photo}
                  className={styles.image}
                />
              ))
            ) : (
              <PhotoView
                className={styles.image}
                locked={!user && item.sensitive}
              />
            )}
          </div>
          <div className={ui.between}>
            <h2>{item.title}</h2>
            <Status status={item.status} />
          </div>
          <p className={styles.description}>{item.description}</p>
          {item.hidden && (
            <span className={ui.badge}>
              {t("숨김 처리된 게시물", "Hidden post")}
            </span>
          )}
        </section>
        <div className={ui.stack}>
          <section className={ui.panel + " " + ui.stack}>
            <div className={ui.between}>
              <h2>{t("발견 정보", "Found at")}</h2>
              <BuildingMap building={item.foundBuilding} />
            </div>
            <BuildingLocation
              building={item.foundBuilding}
              description={item.foundLocationDescription}
            />
            <p className={ui.muted}>
              {t("발견 시각", "Found")}{" "}
              <time dateTime={item.foundAt}>
                {kstDateTime(item.foundAt, lang)}
              </time>
            </p>
          </section>
          <section className={ui.panel + " " + ui.stack}>
            <div className={ui.between}>
              <h2>{t("보관 정보", "Storage location")}</h2>
              {dropOff.data?.building && (
                <BuildingMap building={dropOff.data.building} />
              )}
            </div>
            {checking && <Loading />}
            {!checking && !user && (
              <div className={ui.notice + " " + ui.stack}>
                <span className={ui.row}>
                  <LockKeyhole size={19} />
                  {t(
                    "로그인한 회원만 보관 위치를 볼 수 있어요.",
                    "Sign in to see where this item is kept.",
                  )}
                </span>
                <Link
                  className={ui.secondary}
                  to={signInPath(location.pathname)}
                >
                  {t("로그인", "Sign in")}
                </Link>
              </div>
            )}
            {dropOff.loading && <Loading />}
            {dropOff.error !== undefined && (
              <ErrorState error={dropOff.error} retry={dropOff.reload} />
            )}
            {dropOff.data && (
              <>
                {dropOff.data.building ? (
                  <BuildingLocation
                    building={dropOff.data.building}
                    description={dropOff.data.spotDescription}
                  />
                ) : (
                  <p className={ui.notice}>
                    {t(
                      "습득자가 직접 보관 중이에요.",
                      "The finder is keeping this item.",
                    )}
                  </p>
                )}
                {dropOff.data.photo && (
                  <PhotoView
                    photo={dropOff.data.photo}
                    className={styles.storagePhoto}
                  />
                )}
                <button
                  type="button"
                  className={ui.textButton}
                  aria-expanded={history}
                  onClick={() => showHistory(!history)}
                >
                  {t("보관 위치 변경 이력", "Storage history")}
                </button>
                {history && <LocationHistory path={path} />}
              </>
            )}
          </section>
          <ItemInteractions item={item} changed={reload} />
          <ReportItem itemId={item.itemId} />
          {owner && (
            <section className={ui.panel + " " + ui.stack}>
              <h2>{t("게시물 관리", "Manage post")}</h2>
              <div className={ui.row}>
                <Link className={ui.secondary} to={path + "/edit"}>
                  {t("수정", "Edit")}
                </Link>
                <Link className={ui.secondary} to={path + "/storage"}>
                  {t("보관 위치 변경", "Change storage")}
                </Link>
                {item.status === "EXPIRED" && (
                  <button
                    className={ui.primary}
                    type="button"
                    onClick={() => {
                      action.clear();
                      setConfirm("repost");
                    }}
                  >
                    {t("재등록", "Repost")}
                  </button>
                )}
                <button
                  className={ui.danger}
                  type="button"
                  onClick={() => {
                    action.clear();
                    setConfirm("delete");
                  }}
                >
                  {t("삭제", "Delete")}
                </button>
              </div>
            </section>
          )}
        </div>
      </div>
      {confirm && (
        <Dialog
          title={
            confirm === "delete"
              ? t("이 게시물을 삭제할까요?", "Delete this post?")
              : t("이 물품을 재등록할까요?", "Repost this item?")
          }
          close={() => {
            if (!action.busy) setConfirm(undefined);
          }}
        >
          <div className={ui.stack}>
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              className={confirm === "delete" ? ui.danger : ui.primary}
              disabled={action.busy}
              type="button"
              onClick={() =>
                void action.run(async () => {
                  if (confirm === "delete") {
                    await api.request(path, { method: "DELETE" });
                    navigate("/me/found-items", { replace: true });
                  } else {
                    await api.request(path + "/repost", { method: "POST" });
                    setConfirm(undefined);
                    reload();
                  }
                })
              }
            >
              {confirm === "delete"
                ? t("게시물 삭제", "Delete post")
                : t("재등록", "Repost")}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

export default function FoundDetail() {
  const { itemId } = useParams();
  const item = useRemote<ItemDetail>("/found-items/" + itemId, true);
  if (item.loading) return <Loading />;
  if (item.error !== undefined)
    return <ErrorState error={item.error} retry={item.reload} />;
  if (!item.data) return null;
  return (
    <DetailContent
      key={item.data.itemId}
      item={item.data}
      reload={item.reload}
    />
  );
}
