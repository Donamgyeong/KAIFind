import { useState } from "react";
import { useSession } from "../api/session-context";
import type { Building, Category, Page } from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { Dialog, ErrorState, Loading, Pagination } from "../ui/controls";
import { fieldError } from "../ui/fieldError";
import ui from "../ui/ui.module.css";

type Reference = Building | Category;
function id(reference: Reference) {
  return "buildingId" in reference
    ? reference.buildingId
    : reference.categoryId;
}

function ReferenceForm({
  path,
  kind,
  initial,
  close,
  saved,
}: {
  path: string;
  kind: "buildings" | "categories";
  initial?: Reference;
  close: () => void;
  saved: () => void;
}) {
  const { t, api } = useSession();
  const [code, setCode] = useState(
    initial && "code" in initial ? initial.code : "",
  );
  const [nameKo, setNameKo] = useState(initial?.nameKo ?? "");
  const [nameEn, setNameEn] = useState(initial?.nameEn ?? "");
  const [active, setActive] = useState(initial?.active ?? true);
  const [sensitive, setSensitive] = useState(
    initial && "sensitive" in initial ? initial.sensitive : false,
  );
  const action = useAction();
  const field = (key: string) => fieldError(action.error, key);
  const name =
    kind === "buildings" ? t("건물", "building") : t("카테고리", "category");

  return (
    <Dialog
      title={
        initial
          ? t(name + " 수정", "Edit " + name)
          : t(name + " 추가", "Add " + name)
      }
      close={() => {
        if (!action.busy) close();
      }}
    >
      <form
        className={ui.stack}
        onSubmit={(event) => {
          event.preventDefault();
          void action.run(async () => {
            const names = { nameKo: nameKo.trim(), nameEn: nameEn.trim() };
            const body = initial
              ? { ...names, active }
              : kind === "categories"
                ? { ...names, sensitive }
                : { ...names, code: code.trim().toUpperCase() };
            await api.request(initial ? path + "/" + id(initial) : path, {
              method: initial ? "PATCH" : "POST",
              body,
            });
            saved();
          });
        }}
      >
        {kind === "buildings" && (
          <label className={ui.field}>
            {t("건물 코드", "Building code")}
            <input
              required
              maxLength={30}
              readOnly={!!initial}
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            {field("code") && (
              <span className={ui.fieldError}>{field("code")}</span>
            )}
          </label>
        )}
        <label className={ui.field}>
          {t("한국어 이름", "Korean name")}
          <input
            required
            maxLength={100}
            value={nameKo}
            onChange={(event) => setNameKo(event.target.value)}
          />
          {field("nameKo") && (
            <span className={ui.fieldError}>{field("nameKo")}</span>
          )}
        </label>
        <label className={ui.field}>
          {t("영어 이름", "English name")}
          <input
            required
            maxLength={100}
            value={nameEn}
            onChange={(event) => setNameEn(event.target.value)}
          />
          {field("nameEn") && (
            <span className={ui.fieldError}>{field("nameEn")}</span>
          )}
        </label>
        {initial && (
          <label className={ui.row}>
            <input
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
            />
            {t("활성", "Active")}
          </label>
        )}
        {kind === "categories" && !initial && (
          <label className={ui.row}>
            <input
              type="checkbox"
              checked={sensitive}
              onChange={(event) => setSensitive(event.target.checked)}
            />
            {t("민감 카테고리", "Sensitive category")}
          </label>
        )}
        {action.error !== undefined && <ErrorState error={action.error} />}
        <button type="submit" className={ui.primary} disabled={action.busy}>
          {t("저장", "Save")}
        </button>
      </form>
    </Dialog>
  );
}

export default function AdminReference({
  kind,
}: {
  kind: "buildings" | "categories";
}) {
  const { t } = useSession();
  const [page, setPage] = useState(0);
  const [active, setActive] = useState<"" | "true" | "false">("");
  const [editor, setEditor] = useState<Reference | "new">();
  const path = "/admin/" + kind;
  const records = useRemote<Page<Reference>>(
    path + "?page=" + page + (active ? "&active=" + active : ""),
  );
  return (
    <div className={ui.stack}>
      <div className={ui.between}>
        <label className={ui.field}>
          {t("활성 상태", "Active status")}
          <select
            value={active}
            aria-label={t("활성 상태", "Active status")}
            onChange={(event) => {
              setActive(event.target.value as typeof active);
              setPage(0);
            }}
          >
            <option value="">{t("전체", "All")}</option>
            <option value="true">{t("활성", "Active")}</option>
            <option value="false">{t("비활성", "Inactive")}</option>
          </select>
        </label>
        <button
          className={ui.primary}
          type="button"
          onClick={() => setEditor("new")}
        >
          {kind === "buildings"
            ? t("건물 추가", "Add building")
            : t("카테고리 추가", "Add category")}
        </button>
      </div>
      {records.loading && <Loading />}
      {records.error !== undefined && (
        <ErrorState error={records.error} retry={records.reload} />
      )}
      {records.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("표시할 기준정보가 없어요.", "No reference entries to show.")}
        </p>
      )}
      {records.data?.items.map((record) => (
        <article className={ui.panel + " " + ui.between} key={id(record)}>
          <div className={ui.stack}>
            <strong>
              {"code" in record && record.code + " · "}
              {record.nameKo}
            </strong>
            <p className={ui.muted}>{record.nameEn}</p>
            <div className={ui.row}>
              <span
                className={ui.badge}
                data-status={record.active ? "POSTED" : "EXPIRED"}
              >
                {record.active ? t("활성", "Active") : t("비활성", "Inactive")}
              </span>
              {"sensitive" in record && record.sensitive && (
                <span className={ui.badge}>{t("민감", "Sensitive")}</span>
              )}
            </div>
          </div>
          <button
            type="button"
            className={ui.secondary}
            onClick={() => setEditor(record)}
          >
            {t("수정", "Edit")}
          </button>
        </article>
      ))}
      {records.data && (
        <Pagination
          page={page}
          total={records.data.totalPages}
          change={setPage}
        />
      )}
      {editor && (
        <ReferenceForm
          path={path}
          kind={kind}
          initial={editor === "new" ? undefined : editor}
          close={() => setEditor(undefined)}
          saved={() => {
            setEditor(undefined);
            records.reload();
          }}
        />
      )}
    </div>
  );
}
