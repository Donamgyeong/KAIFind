import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type {
  Building,
  Category,
  LostReport,
  LostReportInput,
} from "../api/types";
import { useAction } from "../api/useAction";
import { useBuildings, useCategories } from "../api/useReferences";
import { useRemote } from "../api/useRemote";
import { ErrorState, Field, Loading } from "../ui/controls";
import DateField from "../ui/DateField";
import dateStyles from "../ui/date-field.module.css";
import { fieldError, requiredFieldsError } from "../ui/fieldError";
import { kstInputValue, localName } from "../ui/format";
import { BuildingPicker, CategorySelect } from "../ui/ReferenceFields";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";

function ReportEditor({
  report,
  categories,
  buildings,
}: {
  report?: LostReport;
  categories: Category[];
  buildings: Building[];
}) {
  const { api, t, lang } = useSession();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<LostReportInput>({
    categoryId: report?.categoryId ?? "",
    description: report?.description ?? "",
    possibleBuildingIds: report?.possibleBuildingIds ?? [],
    lostDateFrom: report?.lostDateFrom ?? "",
    lostDateTo: report?.lostDateTo ?? "",
    privateIdentifyingDetails: report?.privateIdentifyingDetails ?? "",
  });
  const action = useAction();
  const path = report ? "/lost-reports/" + report.reportId : "/lost-reports";

  function change<Key extends keyof LostReportInput>(
    field: Key,
    value: LostReportInput[Key],
  ) {
    setDraft((previous) => ({ ...previous, [field]: value }));
  }
  const field = (key: string) => fieldError(action.error, key);

  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={
          report
            ? t("분실 신고 수정", "Edit lost report")
            : t("분실물 등록", "Report a lost item")
        }
        back={path}
      />
      <form
        className={ui.panel}
        onSubmit={(event) => {
          event.preventDefault();
          void action.run(async () => {
            if (!draft.categoryId) {
              const message = t(
                "물품 분류를 선택해 주세요.",
                "Select a category.",
              );
              throw requiredFieldsError(message, [{ field: "categoryId" }]);
            }
            if (!draft.possibleBuildingIds.length) {
              const message = t(
                "분실 추정 건물을 한 곳 이상 선택해 주세요.",
                "Choose at least one possible building.",
              );
              throw requiredFieldsError(message, [
                { field: "possibleBuildingIds" },
              ]);
            }
            if (!draft.lostDateFrom || !draft.lostDateTo) {
              const message = t(
                "분실 시작일과 종료일을 선택해 주세요.",
                "Select both dates.",
              );
              throw requiredFieldsError(
                message,
                (["lostDateFrom", "lostDateTo"] as const)
                  .filter((key) => !draft[key])
                  .map((field) => ({ field })),
              );
            }
            const saved = await api.request<LostReport>(path, {
              method: report ? "PUT" : "POST",
              body: {
                ...draft,
                description: draft.description.trim(),
                privateIdentifyingDetails:
                  draft.privateIdentifyingDetails.trim(),
              },
            });
            navigate(
              "/lost-reports/" + saved.reportId + (report ? "" : "/created"),
              { replace: true },
            );
          });
        }}
      >
        <fieldset disabled={action.busy} className={ui.fields}>
          <h2>{t("어떤 물건을 잃어버렸나요?", "What did you lose?")}</h2>
          <p className={ui.muted}>
            {t(
              "등록한 정보로 비슷한 습득물을 찾아 알려드려요.",
              "We’ll notify you about similar found items.",
            )}
          </p>
          <Field
            label={t("물품 분류 *", "Category *")}
            error={field("categoryId")}
          >
            <CategorySelect
              label={t("물품 분류", "Category")}
              value={draft.categoryId}
              categories={categories}
              change={(value) => change("categoryId", value)}
            />
          </Field>
          <label className={ui.field}>
            {t("물품 설명 *", "Description *")}
            <textarea
              maxLength={2000}
              required
              value={draft.description}
              onChange={(event) => change("description", event.target.value)}
            />
            {field("description") && (
              <span className={ui.fieldError} role="alert">
                {field("description")}
              </span>
            )}
          </label>
          <Field
            label={t("분실 추정 건물 *", "Possible buildings *")}
            error={field("possibleBuildingIds")}
          >
            {!!draft.possibleBuildingIds.length && (
              <div className={ui.row}>
                {draft.possibleBuildingIds.map((id) => {
                  const building = buildings.find(
                    (entry) => entry.buildingId === id,
                  );
                  const text = building
                    ? building.code + " · " + localName(building, lang)
                    : t("이전에 선택한 건물", "Previously selected building");
                  return (
                    <button
                      key={id}
                      type="button"
                      className={ui.chip}
                      aria-label={t("선택 제거", "Remove") + " " + text}
                      onClick={() =>
                        change(
                          "possibleBuildingIds",
                          draft.possibleBuildingIds.filter(
                            (value) => value !== id,
                          ),
                        )
                      }
                    >
                      {text} ×
                    </button>
                  );
                })}
              </div>
            )}
            <BuildingPicker
              label={t("분실 추정 건물 선택", "Select possible buildings")}
              buildings={buildings}
              values={draft.possibleBuildingIds}
              onChange={(value) => change("possibleBuildingIds", value)}
              multiple
            />
            <p className={ui.muted}>
              {t(
                "여러 건물을 추가할 수 있어요.",
                "You can select multiple buildings.",
              )}
            </p>
          </Field>
          <div className={dateStyles.range}>
            <Field
              label={t("시작 날짜 (KST) *", "Date from (KST) *")}
              error={field("lostDateFrom")}
            >
              <DateField
                label={t("분실 날짜 시작", "Lost date from")}
                value={draft.lostDateFrom}
                max={draft.lostDateTo || kstInputValue().slice(0, 10)}
                onChange={(value) => change("lostDateFrom", value)}
              />
            </Field>
            <span aria-hidden="true">~</span>
            <Field
              label={t("종료 날짜 (KST) *", "Date to (KST) *")}
              error={field("lostDateTo")}
            >
              <DateField
                label={t("분실 날짜 종료", "Lost date to")}
                value={draft.lostDateTo}
                min={draft.lostDateFrom || undefined}
                max={kstInputValue().slice(0, 10)}
                onChange={(value) => change("lostDateTo", value)}
              />
            </Field>
          </div>
          <label className={ui.field}>
            {t("비공개 식별 정보 *", "Private identifying details *")}
            <textarea
              maxLength={1000}
              required
              value={draft.privateIdentifyingDetails}
              placeholder={t(
                "각인, 내용물 등 나만 아는 특징을 적어 주세요.",
                "Add details only you know, such as an engraving.",
              )}
              onChange={(event) =>
                change("privateIdentifyingDetails", event.target.value)
              }
            />
            {field("privateIdentifyingDetails") && (
              <span className={ui.fieldError} role="alert">
                {field("privateIdentifyingDetails")}
              </span>
            )}
          </label>
          <p className={ui.notice}>
            {t(
              "비공개 정보는 본인과 관리자만 볼 수 있어요.",
              "Only you and administrators can view private details.",
            )}
          </p>
          {action.error !== undefined && <ErrorState error={action.error} />}
          <button type="submit" className={ui.primary}>
            {action.busy
              ? t("저장 중…", "Saving…")
              : report
                ? t("수정 저장", "Save changes")
                : t("분실 신고 등록", "Submit lost report")}
          </button>
        </fieldset>
      </form>
    </div>
  );
}

export default function LostForm() {
  const { reportId } = useParams();
  const { t, user, lang } = useSession();
  const report = useRemote<LostReport>(
    reportId ? "/lost-reports/" + reportId : null,
  );
  const categories = useCategories();
  const buildings = useBuildings();
  for (const resource of [report, categories, buildings]) {
    if (resource.error !== undefined)
      return <ErrorState error={resource.error} retry={resource.reload} />;
  }
  if (report.loading || !categories.data || !buildings.data) return <Loading />;
  if (
    report.data &&
    (report.data.ownerId !== user?.userId || report.data.status !== "OPEN")
  ) {
    return (
      <p role="alert">
        {t(
          "진행 중인 본인 신고를 수정할 수 있어요.",
          "You can edit your own open reports.",
        )}
      </p>
    );
  }
  const categoryId = report.data?.categoryId;
  const categoryEntries = categories.data.items;
  const fallback =
    lang === "ko" ? "이전에 선택한 분류" : "Previously selected category";
  const selectable =
    categoryId &&
    !categoryEntries.some((category) => category.categoryId === categoryId)
      ? [
          ...categoryEntries,
          {
            categoryId,
            nameKo: fallback,
            nameEn: fallback,
            active: false,
            sensitive: false,
          },
        ]
      : categoryEntries;
  return (
    <ReportEditor
      key={reportId ?? "new"}
      report={report.data}
      categories={selectable}
      buildings={buildings.data.items}
    />
  );
}
