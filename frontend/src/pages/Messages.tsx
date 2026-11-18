import { MessageCircle, Send } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { Conversation, ItemDetail, Message, Page } from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote, useVisiblePolling } from "../api/useRemote";
import { ErrorState, Loading, Pagination } from "../ui/controls";
import { fieldError } from "../ui/fieldError";
import { dateTime } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";
import styles from "./messages.module.css";

export function ConversationRow({
  conversation,
}: {
  conversation: Conversation;
}) {
  const { t, user, lang } = useSession();
  const item = useRemote<ItemDetail>(
    "/found-items/" + conversation.itemId,
    true,
  );
  return (
    <Link
      className={ui.panel + " " + ui.between}
      to={"/conversations/" + conversation.conversationId}
    >
      <div className={ui.row}>
        <MessageCircle size={21} aria-hidden="true" />
        <div>
          <h2>{item.data?.title ?? t("물품 대화", "Item conversation")}</h2>
          <p className={ui.muted}>
            {conversation.finderId === user?.userId
              ? t("분실자", "Item owner")
              : t("습득자", "Finder")}
          </p>
        </div>
      </div>
      <small className={ui.muted}>
        {dateTime(conversation.updatedAt, lang)}
      </small>
    </Link>
  );
}

export default function Conversations() {
  const { t } = useSession();
  const [params] = useSearchParams();
  const itemId = params.get("itemId");
  const [page, setPage] = useState(0);
  const remote = useRemote<Page<Conversation>>(
    "/conversations?page=" +
      page +
      (itemId ? "&itemId=" + encodeURIComponent(itemId) : ""),
  );
  return (
    <div className={ui.formPage}>
      <SectionTitle title={t("채팅방", "Conversations")} back="/me" />
      {remote.loading && <Loading />}
      {remote.error !== undefined && (
        <ErrorState error={remote.error} retry={remote.reload} />
      )}
      {remote.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("아직 대화가 없어요.", "No conversations yet.")}
        </p>
      )}
      {remote.data?.items.map((conversation) => (
        <ConversationRow
          key={conversation.conversationId}
          conversation={conversation}
        />
      ))}
      {remote.data && (
        <Pagination
          page={page}
          total={remote.data.totalPages}
          change={setPage}
        />
      )}
    </div>
  );
}

function Thread({ id }: { id: string }) {
  const { t, lang, user, api } = useSession();
  const [page, setPage] = useState<number>();
  const [content, setContent] = useState("");
  const action = useAction();
  const path = "/conversations/" + id + "/messages";
  const latest = useRemote<Page<Message>>(path + "?page=0&size=20");
  const lastPage = Math.max(0, (latest.data?.totalPages ?? 1) - 1);
  const index = page ?? lastPage;
  const others = useRemote<Page<Message>>(
    index ? path + "?page=" + index + "&size=20" : null,
  );
  const remote = index ? others : latest;
  useVisiblePolling(latest.reload, latest.error === undefined);
  useVisiblePolling(
    others.reload,
    index === lastPage && index > 0 && others.error === undefined,
  );

  return (
    <div className={ui.formPage}>
      <SectionTitle title={t("메시지", "Messages")} back="/conversations" />
      <section className={ui.panel + " " + ui.stack}>
        {remote.loading && <Loading />}
        {remote.error !== undefined && (
          <ErrorState error={remote.error} retry={remote.reload} />
        )}
        {remote.data?.items.length === 0 && (
          <p className={ui.empty}>
            {t("첫 메시지를 보내 보세요.", "Send the first message.")}
          </p>
        )}
        <ol className={styles.thread}>
          {remote.data?.items.map((message) => (
            <li
              key={message.messageId}
              data-mine={message.senderId === user?.userId}
            >
              <p>{message.content}</p>
              <time dateTime={message.createdAt}>
                {dateTime(message.createdAt, lang)}
              </time>
            </li>
          ))}
        </ol>
        <Pagination
          page={index}
          total={latest.data?.totalPages ?? 0}
          change={setPage}
        />
        {page !== undefined && page !== lastPage && (
          <button
            type="button"
            className={ui.textButton}
            onClick={() => setPage(undefined)}
          >
            {t("최신 메시지", "Latest messages")}
          </button>
        )}
        {remote.data && (
          <form
            className={ui.stack}
            onSubmit={(event) => {
              event.preventDefault();
              void action.run(async () => {
                await api.request(path, {
                  method: "POST",
                  body: { content: content.trim() },
                });
                setContent("");
                setPage(undefined);
                latest.reload();
                others.reload();
              });
            }}
          >
            <label className={ui.field}>
              {t("메시지 입력", "Message")}
              <textarea
                required
                maxLength={2000}
                className={styles.composer}
                value={content}
                disabled={action.busy}
                onChange={(event) => setContent(event.target.value)}
              />
              {fieldError(action.error, "content") && (
                <span className={ui.fieldError}>
                  {fieldError(action.error, "content")}
                </span>
              )}
            </label>
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              type="submit"
              className={ui.primary}
              disabled={action.busy || !content.trim()}
            >
              <Send size={17} />
              {t("보내기", "Send")}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}

export function ConversationMessages() {
  const { conversationId } = useParams();
  return conversationId ? (
    <Thread key={conversationId} id={conversationId} />
  ) : null;
}
