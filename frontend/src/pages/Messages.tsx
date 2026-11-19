import { ChevronRight, MessageCircle } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Link,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useSession } from "../api/session-context";
import type { Conversation, ItemDetail, Message, Page } from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote, useVisiblePolling } from "../api/useRemote";
import { ErrorState, Loading, Pagination } from "../ui/controls";
import { fieldError } from "../ui/fieldError";
import { timeOfDay } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";
import styles from "./messages.module.css";

function roleName(
  conversation: Conversation,
  userId: string | undefined,
  t: (ko: string, en: string) => string,
) {
  return conversation.finderId === userId
    ? t("분실자", "Item owner")
    : t("습득자", "Finder");
}

export function ConversationRow({
  conversation,
  compact = false,
}: {
  conversation: Conversation;
  compact?: boolean;
}) {
  const { t, user } = useSession();
  const location = useLocation();
  const item = useRemote<ItemDetail>(
    "/found-items/" + conversation.itemId,
    true,
  );
  const messagesUrl =
    "/conversations/" + conversation.conversationId + "/messages?size=1";
  const head = useRemote<Page<Message>>(compact ? messagesUrl : null);
  const lastPage = Math.max(0, (head.data?.totalPages ?? 1) - 1);
  const tail = useRemote<Page<Message>>(
    lastPage ? messagesUrl + "&page=" + lastPage : null,
  );
  const latest = (lastPage ? tail.data : head.data)?.items[0];
  const title = item.data
    ? item.data.title + " · " + roleName(conversation, user?.userId, t)
    : t("물품 대화", "Item conversation");

  return (
    <Link
      className={compact ? styles.room : ui.panel + " " + styles.room}
      to={"/conversations/" + conversation.conversationId}
      state={{ conversation, back: location.pathname + location.search }}
    >
      <span className={styles.roomIcon}>
        <MessageCircle size={22} strokeWidth={1.65} aria-hidden="true" />
      </span>
      <div className={styles.roomInfo}>
        <div className={styles.roomTop}>
          <strong>{title}</strong>
          <time dateTime={conversation.updatedAt}>
            {timeOfDay(conversation.updatedAt)}
          </time>
        </div>
        {latest && (
          <p>
            {latest.senderId === user?.userId && t("나: ", "Me: ")}
            {latest.content}
          </p>
        )}
      </div>
      <ChevronRight
        size={18}
        strokeWidth={1.65}
        className={styles.roomArrow}
        aria-hidden="true"
      />
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
  const { t, user, api } = useSession();
  const location = useLocation();
  const hint = location.state as {
    conversation?: Conversation;
    back?: string;
  } | null;
  const [conversation, setConversation] = useState<Conversation | undefined>(
    hint?.conversation?.conversationId === id ? hint.conversation : undefined,
  );
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
  const item = useRemote<ItemDetail>(
    conversation ? "/found-items/" + conversation.itemId : null,
    true,
  );
  useVisiblePolling(latest.reload, latest.error === undefined);
  useVisiblePolling(
    others.reload,
    index === lastPage && index > 0 && others.error === undefined,
  );

  useEffect(() => {
    if (conversation?.conversationId === id) return;
    const abort = new AbortController();
    async function findConversation() {
      let page = 0;
      while (!abort.signal.aborted) {
        const result = await api.request<Page<Conversation>>(
          "/conversations?size=100&page=" + page,
          { signal: abort.signal },
        );
        const match = result.items.find((entry) => entry.conversationId === id);
        if (match) {
          if (!abort.signal.aborted) setConversation(match);
          return;
        }
        if (++page >= result.totalPages) return;
      }
    }
    void findConversation().catch(() => {});
    return () => abort.abort();
  }, [api, conversation?.conversationId, id]);

  const title =
    conversation && item.data
      ? item.data.title + " · " + roleName(conversation, user?.userId, t)
      : t("메시지", "Messages");
  const back =
    hint?.back?.startsWith("/") && !hint.back.startsWith("//")
      ? hint.back
      : "/me";

  return (
    <div className={styles.chat}>
      <div className={styles.chatHeading}>
        <SectionTitle title={title} back={back} />
      </div>
      <div className={styles.history}>
        {remote.loading && <Loading />}
        {remote.error !== undefined && (
          <ErrorState error={remote.error} retry={remote.reload} />
        )}
        <ol
          className={styles.thread}
          aria-label={t("대화 내역", "Message history")}
        >
          {remote.data?.items.map((message) => (
            <li
              key={message.messageId}
              data-mine={message.senderId === user?.userId}
            >
              <p>{message.content}</p>
              <time dateTime={message.createdAt}>
                {timeOfDay(message.createdAt)}
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
      </div>
      {remote.data && (
        <form
          className={styles.composer}
          onSubmit={(event) => {
            event.preventDefault();
            if (!content.trim()) return;
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
          <textarea
            required
            maxLength={2000}
            rows={1}
            aria-label={t("메시지 입력", "Message")}
            placeholder={t("메시지를 입력하세요", "Type a message")}
            value={content}
            disabled={action.busy}
            onChange={(event) => setContent(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button
            type="submit"
            aria-label={t("보내기", "Send")}
            disabled={action.busy || !content.trim()}
          >
            <ChevronRight size={24} strokeWidth={1.65} aria-hidden="true" />
          </button>
          {fieldError(action.error, "content") && (
            <span className={ui.fieldError}>
              {fieldError(action.error, "content")}
            </span>
          )}
          {action.error !== undefined && <ErrorState error={action.error} />}
        </form>
      )}
    </div>
  );
}

export function ConversationMessages() {
  const { conversationId } = useParams();
  return conversationId ? (
    <Thread key={conversationId} id={conversationId} />
  ) : null;
}
