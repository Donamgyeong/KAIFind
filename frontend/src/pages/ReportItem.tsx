import { Flag } from "lucide-react";
import { useState } from "react";
import { useSession } from "../api/session-context";
import type { ReportReason } from "../api/types";
import { useAction } from "../api/useAction";
import { Dialog, ErrorState } from "../ui/controls";
import { fieldError } from "../ui/fieldError";
import ui from "../ui/ui.module.css";

export default function ReportItem({ itemId }: { itemId: string }) {
  const { api, t, user } = useSession();
  const [opened, setOpened] = useState(false);
  const [sent, setSent] = useState(false);
  const [reasonCode, setReason] = useState<ReportReason>("INAPPROPRIATE");
  const [details, setDetails] = useState("");
  const action = useAction();
  if (!user) return null;
  return (
    <>
      <button
        type="button"
        className={ui.textButton}
        onClick={() => {
          setOpened(true);
          setSent(false);
          action.clear();
        }}
      >
        <Flag size={16} aria-hidden="true" /> {t("게시물 신고", "Report post")}
      </button>
      {sent && (
        <p role="status" className={ui.notice}>
          {t("신고를 접수했어요.", "Report submitted.")}
        </p>
      )}
      {opened && (
        <Dialog
          title={t("게시물 신고", "Report post")}
          close={() => {
            if (!action.busy) setOpened(false);
          }}
        >
          <form
            className={ui.stack}
            onSubmit={(event) => {
              event.preventDefault();
              void action.run(async () => {
                await api.request("/found-items/" + itemId + "/reports", {
                  method: "POST",
                  body: { reasonCode, details: details.trim() },
                });
                setDetails("");
                setOpened(false);
                setSent(true);
              });
            }}
          >
            <label className={ui.field}>
              {t("신고 사유", "Reason")}
              <select
                value={reasonCode}
                onChange={(event) =>
                  setReason(event.target.value as ReportReason)
                }
              >
                <option value="INAPPROPRIATE">
                  {t("부적절한 게시물", "Inappropriate post")}
                </option>
                <option value="SPAM">{t("스팸", "Spam")}</option>
                <option value="OTHER">{t("기타", "Other")}</option>
              </select>
              {fieldError(action.error, "reasonCode") && (
                <span className={ui.fieldError}>
                  {fieldError(action.error, "reasonCode")}
                </span>
              )}
            </label>
            <label className={ui.field}>
              {t("상세 설명", "Details")}
              <textarea
                required
                maxLength={1000}
                value={details}
                onChange={(event) => setDetails(event.target.value)}
              />
              {fieldError(action.error, "details") && (
                <span className={ui.fieldError}>
                  {fieldError(action.error, "details")}
                </span>
              )}
            </label>
            {action.error !== undefined && <ErrorState error={action.error} />}
            <button
              type="submit"
              className={ui.primary}
              disabled={action.busy || !details.trim()}
            >
              {t("신고 제출", "Submit report")}
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
}
