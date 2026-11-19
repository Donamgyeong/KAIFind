import { MessageCircle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useSession } from "../api/session-context";
import type {
  Collection,
  Conversation,
  Dispute,
  ItemDetail,
  Page,
} from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { Dialog, ErrorState, Loading, Pagination } from "../ui/controls";
import { fieldError } from "../ui/fieldError";
import { kstDateTime } from "../ui/format";
import ui from "../ui/ui.module.css";

export function StartConversation({ item }: { item: ItemDetail }) {
  const { t, api, user } = useSession();
  const action = useAction();
  const navigate = useNavigate();
  if (!user || item.status !== "POSTED" || item.hidden) return null;
  if (item.finder.userId === user.userId) {
    return (
      <Link
        className={ui.secondary}
        to={"/conversations?itemId=" + item.itemId}
      >
        <MessageCircle size={18} />
        {t("이 물품의 대화", "Conversations about this item")}
      </Link>
    );
  }
  return (
    <>
      <button
        type="button"
        className={ui.secondary}
        disabled={action.busy}
        onClick={() =>
          void action.run(async () => {
            const conversation = await api.request<Conversation>(
              "/conversations",
              { method: "POST", body: { itemId: item.itemId } },
            );
            navigate("/conversations/" + conversation.conversationId, {
              state: { conversation, back: "/found-items/" + item.itemId },
            });
          })
        }
      >
        <MessageCircle size={18} />
        {t("습득자에게 메시지", "Message the finder")}
      </button>
      {action.error !== undefined && <ErrorState error={action.error} />}
    </>
  );
}

function DisputeList({ path }: { path: string }) {
  const { t, lang } = useSession();
  const [page, setPage] = useState(0);
  const disputes = useRemote<Page<Dispute>>(path + "/disputes?page=" + page);
  return (
    <div className={ui.stack}>
      {disputes.loading && <Loading />}
      {disputes.error !== undefined && (
        <ErrorState error={disputes.error} retry={disputes.reload} />
      )}
      {disputes.data?.items.length === 0 && (
        <p className={ui.muted}>
          {t(
            "수거 이의 제기 이력이 없어요.",
            "No collection disputes have been filed.",
          )}
        </p>
      )}
      {disputes.data?.items.map((entry) => (
        <article key={entry.disputeId} className={ui.notice + " " + ui.stack}>
          <span>
            {entry.status === "OPEN"
              ? t("검토 대기", "Awaiting review")
              : entry.decision === "UPHELD"
                ? t("이의 인정", "Upheld")
                : t("이의 기각", "Dismissed")}
          </span>
          <p className={ui.userText}>{entry.reason}</p>
          <small>{kstDateTime(entry.createdAt, lang)}</small>
        </article>
      ))}
      {disputes.data && (
        <Pagination
          page={page}
          total={disputes.data.totalPages}
          change={setPage}
        />
      )}
    </div>
  );
}

export default function ItemInteractions({
  item,
  changed,
}: {
  item: ItemDetail;
  changed: () => void;
}) {
  const { t, api, user, lang } = useSession();
  const path = "/found-items/" + item.itemId;
  const [mode, setMode] = useState<"collect" | "cancel" | "dispute">();
  const [confirmed, setConfirmed] = useState(false);
  const [history, setHistory] = useState(false);
  const [disputeRevision, setDisputeRevision] = useState(0);
  const [reason, setReason] = useState("");
  const [success, setSuccess] = useState("");
  const action = useAction();
  const collection = useRemote<Collection>(
    user && item.status === "COLLECTED" ? path + "/collection" : null,
  );
  const owner = user?.userId === item.finder.userId;

  if (
    !user ||
    (!owner &&
      item.status !== "COLLECTED" &&
      (item.status !== "POSTED" || item.hidden))
  )
    return null;
  const expectedError =
    collection.error instanceof ApiError &&
    [403, 404].includes(collection.error.status);

  function open(next: typeof mode) {
    action.clear();
    setConfirmed(false);
    setReason("");
    setSuccess("");
    setMode(next);
  }

  return (
    <div className={ui.stack}>
      {item.status === "POSTED" && !item.hidden && (
        <>
          <StartConversation item={item} />
          <button
            type="button"
            className={ui.primary}
            onClick={() => open("collect")}
          >
            {t("수령 완료", "Mark as collected")}
          </button>
        </>
      )}
      {collection.loading && <Loading />}
      {collection.error !== undefined && !expectedError && (
        <ErrorState error={collection.error} retry={collection.reload} />
      )}
      {item.status === "COLLECTED" && (
        <p className={ui.notice}>
          {t("수령이 완료된 물품이에요.", "This item has been collected.")}
          {collection.data &&
            " " + kstDateTime(collection.data.collectedAt, lang)}
        </p>
      )}
      {collection.data && (
        <div className={ui.row}>
          <button
            type="button"
            className={ui.secondary}
            onClick={() => open("cancel")}
          >
            {t("수거 취소", "Undo collection")}
          </button>
          {owner && (
            <button
              type="button"
              className={ui.secondary}
              onClick={() => open("dispute")}
            >
              {t("수거 이의 제기", "Dispute collection")}
            </button>
          )}
        </div>
      )}
      {owner && (
        <>
          <button
            type="button"
            className={ui.textButton}
            aria-expanded={history}
            onClick={() => setHistory(!history)}
          >
            {t("수거 이의 제기 이력", "Collection dispute history")}
          </button>
          {history && <DisputeList key={disputeRevision} path={path} />}
        </>
      )}
      {success && (
        <p className={ui.notice} role="status">
          {success}
        </p>
      )}
      {mode && (
        <Dialog
          title={
            mode === "collect"
              ? t("물품을 직접 수령하셨나요?", "Did you pick up the item?")
              : mode === "cancel"
                ? t("수거를 취소할까요?", "Undo this collection?")
                : t("수거 이의 제기", "Dispute collection")
          }
          close={() => {
            if (!action.busy) setMode(undefined);
          }}
        >
          <form
            className={ui.stack}
            onSubmit={(event) => {
              event.preventDefault();
              void action.run(async () => {
                if (mode === "collect" && !confirmed) return;
                if (mode === "dispute") {
                  await api.request(path + "/disputes", {
                    method: "POST",
                    body: { reason: reason.trim() },
                  });
                  setHistory(true);
                  setDisputeRevision((value) => value + 1);
                  setSuccess(
                    t(
                      "이의 제기를 접수했어요.",
                      "Collection dispute submitted.",
                    ),
                  );
                } else {
                  try {
                    await api.request(
                      path + "/collection",
                      mode === "collect"
                        ? { method: "POST", body: { confirmedOwnership: true } }
                        : { method: "DELETE" },
                    );
                  } catch (error) {
                    if (
                      error instanceof ApiError &&
                      [
                        "ALREADY_COLLECTED",
                        "ITEM_NOT_POSTED",
                        "ITEM_NOT_COLLECTED",
                      ].includes(error.code)
                    )
                      changed();
                    throw error;
                  }
                  changed();
                  setSuccess(
                    mode === "collect"
                      ? t("수령을 완료했어요.", "Item marked as collected.")
                      : t("수거를 취소했어요.", "Collection undone."),
                  );
                }
                setMode(undefined);
              });
            }}
          >
            {mode === "collect" && (
              <>
                <p>
                  {t(
                    "수령 완료 후 이 물품은 기본 검색 결과에서 제외되고 습득자에게 알림이 전송돼요.",
                    "This item will leave default search results, and the finder will be notified.",
                  )}
                </p>
                <label className={ui.row}>
                  <input
                    type="checkbox"
                    required
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  {t(
                    "직접 수령했고 제 물품임을 확인했어요.",
                    "I collected this item and confirm it is mine.",
                  )}
                </label>
              </>
            )}
            {mode === "dispute" && (
              <label className={ui.field}>
                {t("이의 사유", "Reason")}
                <textarea
                  required
                  maxLength={1000}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
                {fieldError(action.error, "reason") && (
                  <span className={ui.fieldError}>
                    {fieldError(action.error, "reason")}
                  </span>
                )}
              </label>
            )}
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              type="submit"
              className={ui.primary}
              disabled={action.busy || (mode === "collect" && !confirmed)}
            >
              {mode === "collect"
                ? t("수령 완료", "Confirm collection")
                : mode === "cancel"
                  ? t("수거 취소", "Undo collection")
                  : t("이의 제출", "Submit dispute")}
            </button>
          </form>
        </Dialog>
      )}
    </div>
  );
}
