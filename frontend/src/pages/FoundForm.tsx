import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { Api } from "../api/client";
import { ApiError } from "../api/client";
import { useSession } from "../api/session-context";
import type {
  Building,
  Category,
  DropOff,
  DropOffInput,
  ItemDetail,
  PhotoAttachment,
} from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { BuildingPicker, ErrorState, Field, Loading } from "../ui/controls";
import { fieldError } from "../ui/fieldError";
import { kstInputValue } from "../ui/format";
import PhotoInputs from "../ui/PhotoInputs";
import type { PhotoDraft } from "../ui/PhotoInputs";
import { CategorySelect } from "../ui/ReferenceFields";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";

interface Draft {
  categoryId: string;
  title: string;
  description: string;
  foundBuildingId: string;
  foundLocationDescription: string;
  foundAt: string;
}

interface StorageDraft {
  mode: DropOffInput["mode"];
  buildingId: string;
  spotDescription: string;
  photos: PhotoDraft[];
}

function initialStorage(location?: DropOff): StorageDraft {
  return {
    mode: location?.mode ?? "DROP_OFF",
    buildingId: location?.building?.buildingId ?? "",
    spotDescription: location?.spotDescription ?? "",
    photos: [],
  };
}

function withCurrent<T>(
  items: T[],
  existing: T | null | undefined,
  id: (item: T) => string,
) {
  return existing && !items.some((item) => id(item) === id(existing))
    ? [existing, ...items]
    : items;
}

async function upload(
  api: Api,
  photos: PhotoDraft[],
  purpose: "ITEM" | "DROP_OFF",
  uploads: Map<string, string>,
): Promise<PhotoAttachment[]> {
  const results: PhotoAttachment[] = [];
  for (const photo of photos) {
    let photoId = photo.existing?.photoId ?? uploads.get(photo.key);
    if (!photoId && photo.file) {
      const form = new FormData();
      form.set("file", photo.file);
      form.set("purpose", purpose);
      const uploaded = await api.request<{ photoId: string }>("/photos", {
        method: "POST",
        body: form,
      });
      photoId = uploaded.photoId;
      uploads.set(photo.key, photoId);
    }
    if (!photoId) throw new Error("Missing photo ID");
    results.push({ photoId, altText: photo.altText.trim() });
  }
  return results;
}

async function storageInput(
  api: Api,
  storage: StorageDraft,
  uploads: Map<string, string>,
): Promise<DropOffInput> {
  if (storage.mode === "KEPT_BY_FINDER") return { mode: storage.mode };
  const [photo] = await upload(api, storage.photos, "DROP_OFF", uploads);
  return {
    mode: storage.mode,
    buildingId: storage.buildingId,
    spotDescription: storage.spotDescription.trim(),
    ...(photo ? { photo } : {}),
  };
}

function LocationFields({
  value,
  change,
  buildings,
  error,
  prefix = "",
  editing = false,
}: {
  value: StorageDraft;
  change: (value: StorageDraft) => void;
  buildings: Building[];
  error: unknown;
  prefix?: string;
  editing?: boolean;
}) {
  const { t } = useSession();
  const fields = (key: string) => fieldError(error, prefix + key);
  return (
    <div className={ui.stack}>
      <h2>{t("습득 물품 보관", "Item storage")}</h2>
      <div className={ui.segment}>
        <button
          type="button"
          aria-pressed={value.mode === "DROP_OFF"}
          onClick={() => change({ ...value, mode: "DROP_OFF" })}
        >
          {t("보관", "Drop off")}
        </button>
        <button
          type="button"
          aria-pressed={value.mode === "KEPT_BY_FINDER"}
          onClick={() => change({ ...value, mode: "KEPT_BY_FINDER" })}
        >
          {t("직접 보관", "Keep with me")}
        </button>
      </div>
      {value.mode === "DROP_OFF" ? (
        <>
          <Field
            label={t("보관 건물 *", "Drop-off building *")}
            error={fields("buildingId")}
          >
            <BuildingPicker
              label={t("보관 건물을 선택해 주세요", "Select drop-off building")}
              buildings={buildings}
              values={value.buildingId ? [value.buildingId] : []}
              onChange={([buildingId]) => change({ ...value, buildingId })}
            />
          </Field>
          <label className={ui.field}>
            {t("보관 위치 *", "Drop-off spot *")}
            <input
              required
              maxLength={300}
              value={value.spotDescription}
              placeholder={t(
                "예: 1층 안내데스크",
                "e.g. Ground-floor reception",
              )}
              onChange={(event) =>
                change({ ...value, spotDescription: event.target.value })
              }
            />
            {fields("spotDescription") && (
              <span className={ui.fieldError} role="alert">
                {fields("spotDescription")}
              </span>
            )}
          </label>
          <Field
            label={t(
              "보관 위치 사진 (선택)",
              "Photo of the drop-off spot (optional)",
            )}
            error={fields("photo")}
          >
            {editing && (
              <p className={ui.muted}>
                {t(
                  "새 보관 이력에 사용할 사진을 첨부할 수 있어요.",
                  "Attach a photo for this new storage entry.",
                )}
              </p>
            )}
            <PhotoInputs
              values={value.photos}
              change={(photos) => change({ ...value, photos })}
              max={1}
            />
          </Field>
        </>
      ) : (
        <p className={ui.notice}>
          {t(
            "분실자가 KAIFind 메시지로 연락할 수 있어요.",
            "The owner can contact you through KAIFind messages.",
          )}
        </p>
      )}
    </div>
  );
}

function FoundItemEditor({
  item,
  buildings,
  categories,
}: {
  item?: ItemDetail;
  buildings: Building[];
  categories: Category[];
}) {
  const { t, api, lang } = useSession();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Draft>({
    title: item?.title ?? "",
    description: item?.description ?? "",
    categoryId: item?.category.categoryId ?? "",
    foundBuildingId: item?.foundBuilding.buildingId ?? "",
    foundLocationDescription: item?.foundLocationDescription ?? "",
    foundAt: item ? kstInputValue(item.foundAt) : "",
  });
  const [photos, setPhotos] = useState<PhotoDraft[]>(
    () =>
      item?.photos.map((photo) => ({
        key: photo.photoId,
        altText: photo.altText,
        existing: photo,
      })) ?? [],
  );
  const [location, setLocation] = useState<StorageDraft>(initialStorage);
  const uploads = useRef(new Map<string, string>());
  const action = useAction();
  const field = (key: keyof Draft, value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const detailPath = item ? "/found-items/" + item.itemId : "/me/found-items";
  const error = (key: string) => fieldError(action.error, key);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await action.run(async () => {
      const missing = [
        !draft.foundBuildingId && {
          field: "foundBuildingId",
          message: t(
            "발견 건물을 선택해 주세요.",
            "Select the found building.",
          ),
        },
        photos.length === 0 && {
          field: "photos",
          message: t(
            "사진을 한 장 이상 첨부해 주세요.",
            "Attach at least one photo.",
          ),
        },
        !item &&
          location.mode === "DROP_OFF" &&
          !location.buildingId && {
            field: "dropOff.buildingId",
            message: t(
              "보관 건물을 선택해 주세요.",
              "Select a drop-off building.",
            ),
          },
      ].filter((value): value is { field: string; message: string } =>
        Boolean(value),
      );
      if (missing.length)
        throw new ApiError(
          400,
          "VALIDATION_ERROR",
          t("필수 항목을 확인해 주세요.", "Check the required fields."),
          missing.map((value) => ({ ...value, code: "REQUIRED" })),
        );

      const payload = {
        ...draft,
        title: draft.title.trim(),
        description: draft.description.trim(),
        foundLocationDescription: draft.foundLocationDescription.trim(),
        foundAt: draft.foundAt + ":00+09:00",
      };
      if (item && kstInputValue(item.foundAt) === draft.foundAt)
        payload.foundAt = item.foundAt;
      try {
        const attachments = await upload(api, photos, "ITEM", uploads.current);
        if (item) {
          const previous = {
            title: item.title,
            categoryId: item.category.categoryId,
            description: item.description,
            foundBuildingId: item.foundBuilding.buildingId,
            foundAt: item.foundAt,
            foundLocationDescription: item.foundLocationDescription,
          };
          const changes: Record<string, unknown> = {};
          for (const key of Object.keys(payload) as (keyof Draft)[]) {
            if (payload[key] !== previous[key]) changes[key] = payload[key];
          }
          if (
            JSON.stringify(attachments) !==
            JSON.stringify(
              item.photos.map(({ photoId, altText }) => ({ photoId, altText })),
            )
          )
            changes.photos = attachments;
          if (Object.keys(changes).length)
            await api.request(detailPath, { method: "PATCH", body: changes });
          navigate(detailPath, { replace: true });
          return;
        }
        const dropOff = await storageInput(api, location, uploads.current);
        const created = await api.request<ItemDetail>("/found-items", {
          method: "POST",
          body: { ...payload, photos: attachments, dropOff },
        });
        navigate("/found-items/" + created.itemId + "/created", {
          replace: true,
        });
      } catch (failure) {
        if (
          failure instanceof ApiError &&
          ["INVALID_REFERENCE", "PHOTO_ALREADY_ATTACHED"].includes(failure.code)
        )
          uploads.current.clear();
        throw failure;
      }
    });
  }

  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={
          item
            ? t("습득물 수정", "Edit found item")
            : t("습득물 등록", "Post a found item")
        }
        back={detailPath}
      />
      <form
        className={ui.panel + " " + ui.stack}
        onSubmit={(event) => void submit(event)}
      >
        <fieldset disabled={action.busy} className={ui.fields}>
          {!item && (
            <>
              <h2>{t("무엇을 주웠나요?", "What did you find?")}</h2>
              <p className={ui.muted}>
                {t(
                  "물품과 발견 장소를 알려 주세요.",
                  "Tell us about the item and where you found it.",
                )}
              </p>
            </>
          )}
          <Field
            label={t("물품 사진 *", "Item photos *")}
            error={error("photos")}
          >
            <PhotoInputs values={photos} change={setPhotos} max={5} required />
          </Field>
          <label className={ui.field}>
            {t("물품 이름 *", "Item name *")}
            <input
              required
              maxLength={100}
              value={draft.title}
              onChange={(event) => field("title", event.target.value)}
            />
            {error("title") && (
              <span role="alert" className={ui.fieldError}>
                {error("title")}
              </span>
            )}
          </label>
          <Field
            label={t("물품 분류 *", "Category *")}
            error={error("categoryId")}
          >
            <CategorySelect
              label={t("물품 분류", "Category")}
              categories={withCurrent(
                categories,
                item?.category,
                (value) => value.categoryId,
              )}
              value={draft.categoryId}
              change={(value) => field("categoryId", value)}
            />
          </Field>
          {categories.find(
            (category) => category.categoryId === draft.categoryId,
          )?.sensitive && (
            <p className={ui.notice}>
              {t(
                "민감 물품의 사진은 로그인한 회원만 볼 수 있어요.",
                "Only signed-in members can view photos of sensitive items.",
              )}
            </p>
          )}
          <label className={ui.field}>
            {t("물품 설명 *", "Description *")}
            <textarea
              required
              maxLength={2000}
              value={draft.description}
              placeholder={t(
                "색상, 특징, 발견 상황을 적어 주세요.",
                "Describe its color, identifying features and how you found it.",
              )}
              onChange={(event) => field("description", event.target.value)}
            />
            {error("description") && (
              <span role="alert" className={ui.fieldError}>
                {error("description")}
              </span>
            )}
          </label>
          <Field
            label={t("발견 건물 *", "Found building *")}
            error={error("foundBuildingId")}
          >
            <BuildingPicker
              label={t("발견 건물 선택", "Select found building")}
              buildings={withCurrent(
                buildings,
                item?.foundBuilding,
                (value) => value.buildingId,
              )}
              values={draft.foundBuildingId ? [draft.foundBuildingId] : []}
              onChange={([value]) => field("foundBuildingId", value)}
            />
          </Field>
          <label className={ui.field}>
            {t("발견 위치 *", "Found location *")}
            <input
              required
              maxLength={300}
              value={draft.foundLocationDescription}
              placeholder={t(
                "예: 1층 입구 벤치",
                "e.g. Bench near the main entrance",
              )}
              onChange={(event) =>
                field("foundLocationDescription", event.target.value)
              }
            />
            {error("foundLocationDescription") && (
              <span role="alert" className={ui.fieldError}>
                {error("foundLocationDescription")}
              </span>
            )}
          </label>
          <label className={ui.field}>
            {t("발견 날짜·시각 (KST) *", "Found date and time (KST) *")}
            <input
              type="datetime-local"
              required
              value={draft.foundAt}
              lang={lang}
              onChange={(event) => field("foundAt", event.target.value)}
            />
            {error("foundAt") && (
              <span role="alert" className={ui.fieldError}>
                {error("foundAt")}
              </span>
            )}
          </label>
          {!item && (
            <LocationFields
              value={location}
              change={setLocation}
              buildings={buildings}
              error={action.error}
              prefix="dropOff."
            />
          )}
          {action.error !== undefined && <ErrorState error={action.error} />}
          <button className={ui.primary} type="submit">
            {action.busy
              ? t("저장 중…", "Saving…")
              : item
                ? t("저장", "Save")
                : t("습득물 등록하기", "Post found item")}
          </button>
        </fieldset>
      </form>
    </div>
  );
}

export default function FoundForm() {
  const { itemId } = useParams();
  const { user, t } = useSession();
  const item = useRemote<ItemDetail>(itemId ? "/found-items/" + itemId : null);
  const categories = useRemote<{ items: Category[] }>("/categories", true);
  const buildings = useRemote<{ items: Building[] }>("/buildings", true);
  if (item.error !== undefined)
    return <ErrorState error={item.error} retry={item.reload} />;
  if (categories.error !== undefined)
    return <ErrorState error={categories.error} retry={categories.reload} />;
  if (buildings.error !== undefined)
    return <ErrorState error={buildings.error} retry={buildings.reload} />;
  if (!categories.data || !buildings.data || item.loading) return <Loading />;
  if (item.data && item.data.finder.userId !== user?.userId)
    return (
      <p role="alert">
        {t("작성자만 수정할 수 있어요.", "Only the finder can edit this item.")}
      </p>
    );
  return (
    <FoundItemEditor
      key={itemId ?? "new"}
      item={item.data}
      buildings={buildings.data.items}
      categories={categories.data.items}
    />
  );
}

function StorageEditor({
  itemId,
  value,
  buildings,
}: {
  itemId: string;
  value: DropOff;
  buildings: Building[];
}) {
  const { api, t } = useSession();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(() => initialStorage(value));
  const uploads = useRef(new Map<string, string>());
  const action = useAction();
  const path = "/found-items/" + itemId;
  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={t("보관 위치 변경", "Change storage location")}
        back={path}
      />
      <form
        className={ui.panel}
        onSubmit={(event) => {
          event.preventDefault();
          void action.run(async () => {
            if (draft.mode === "DROP_OFF" && !draft.buildingId) {
              const message = t(
                "보관 건물을 선택해 주세요.",
                "Select a drop-off building.",
              );
              throw new ApiError(400, "VALIDATION_ERROR", message, [
                { field: "buildingId", code: "REQUIRED", message },
              ]);
            }
            await api.request(path + "/drop-off", {
              method: "PUT",
              body: await storageInput(api, draft, uploads.current),
            });
            navigate(path, { replace: true });
          });
        }}
      >
        <fieldset disabled={action.busy} className={ui.fields}>
          <LocationFields
            value={draft}
            change={setDraft}
            buildings={buildings}
            error={action.error}
            editing
          />
          {action.error !== undefined && <ErrorState error={action.error} />}
          <button type="submit" className={ui.primary}>
            {t("보관 위치 저장", "Save storage location")}
          </button>
        </fieldset>
      </form>
    </div>
  );
}

export function ChangeStorage() {
  const { itemId } = useParams();
  const { user, t } = useSession();
  const path = "/found-items/" + itemId;
  const item = useRemote<ItemDetail>(path);
  const dropOff = useRemote<DropOff>(
    item.data?.finder.userId === user?.userId ? path + "/drop-off" : null,
  );
  const buildings = useRemote<{ items: Building[] }>("/buildings", true);
  for (const resource of [item, dropOff, buildings]) {
    if (resource.error !== undefined)
      return <ErrorState error={resource.error} retry={resource.reload} />;
  }
  if (item.data && item.data.finder.userId !== user?.userId)
    return (
      <p role="alert">
        {t("작성자만 수정할 수 있어요.", "Only the finder can edit this item.")}
      </p>
    );
  if (!dropOff.data || !buildings.data || !itemId) return <Loading />;
  return (
    <StorageEditor
      key={itemId}
      itemId={itemId}
      value={dropOff.data}
      buildings={withCurrent(
        buildings.data.items,
        dropOff.data.building,
        (building) => building.buildingId,
      )}
    />
  );
}

export function FoundCreated() {
  const { itemId } = useParams();
  const { user, t } = useSession();
  const path = "/found-items/" + itemId;
  const item = useRemote<ItemDetail>(path);
  const dropOff = useRemote<DropOff>(
    item.data?.finder.userId === user?.userId ? path + "/drop-off" : null,
  );
  if (item.error !== undefined)
    return <ErrorState error={item.error} retry={item.reload} />;
  if (!item.data) return <Loading />;
  if (item.data.finder.userId !== user?.userId)
    return <Link to={path}>{t("물품 상세 보기", "View item")}</Link>;
  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={t("습득 신고", "Found items")}
        back="/me/found-items"
      />
      <section className={ui.panel + " " + ui.stack}>
        <h2>{t("습득물 등록을 완료했어요", "Found item posted")}</h2>
        <p className={ui.muted}>
          {t(
            "등록한 습득물 정보를 확인해 주세요.",
            "Review the item you posted.",
          )}
        </p>
        <h3>{item.data.title}</h3>
        <p>
          {item.data.foundBuilding.code} · {item.data.foundLocationDescription}
        </p>
        {dropOff.data && (
          <p>
            {dropOff.data.mode === "KEPT_BY_FINDER"
              ? t("직접 보관 중", "Kept by finder")
              : dropOff.data.spotDescription}
          </p>
        )}
        <Link to={path} className={ui.primary}>
          {t("물품 상세 보기", "View item")}
        </Link>
        <Link to="/me/found-items" className={ui.secondary}>
          {t("내 습득 신고", "My found items")}
        </Link>
      </section>
    </div>
  );
}
