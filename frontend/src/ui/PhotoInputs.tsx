import { Camera, ImagePlus, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { useSession } from "../api/session-context";
import type { Photo } from "../api/types";
import PhotoView from "./PhotoView";
import styles from "./ui.module.css";

const photoFormats = {
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
  "image/webp": [".webp"],
};
const photoMimeTypes = Object.keys(photoFormats);
const photoExtensions = Object.values(photoFormats).flat();
const photoAccept = [...photoMimeTypes, ...photoExtensions].join(",");

export interface PhotoDraft {
  key: string;
  altText: string;
  file?: File;
  existing?: Photo;
}

function LocalPreview({ file, alt }: { file: File; alt: string }) {
  const [image, setImage] = useState<{ file: File; url: string }>();
  useEffect(() => {
    const url = URL.createObjectURL(file);
    void Promise.resolve().then(() => setImage({ file, url }));
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return image?.file === file ? (
    <img className={styles.photoPreview} src={image.url} alt={alt} />
  ) : null;
}

export default function PhotoInputs({
  values,
  change,
  max,
  required = false,
  choose = true,
}: {
  values: PhotoDraft[];
  change: (values: PhotoDraft[]) => void;
  max: number;
  required?: boolean;
  choose?: boolean;
}) {
  const { t } = useSession();
  const [problem, setProblem] = useState("");
  function add(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const files = input.files;
    if (!files?.length) return;
    const accepted = [...files].filter((file) => {
      const extension = file.name
        .slice(file.name.lastIndexOf("."))
        .toLowerCase();
      return (
        (!file.type || photoMimeTypes.includes(file.type)) &&
        photoExtensions.includes(extension)
      );
    });
    const next = accepted.slice(0, max - values.length);
    setProblem(
      accepted.length !== files.length
        ? t(
            "JPG, PNG, WebP 사진을 선택해 주세요.",
            "Choose a JPG, PNG or WebP image.",
          )
        : next.length !== accepted.length
          ? t(
              "첨부 가능한 사진 수를 초과했어요.",
              "The photo limit has been reached.",
            )
          : "",
    );
    if (next.length)
      change([
        ...values,
        ...next.map((file) => ({
          key: crypto.randomUUID(),
          altText: "",
          file,
        })),
      ]);
    input.value = "";
  }

  return (
    <div className={styles.stack}>
      {choose && values.length < max && (
        <div className={styles.upload}>
          <label className={styles.uploadChoice}>
            <ImagePlus size={25} />
            <span>{t("사진 업로드", "Upload photos")}</span>
            <input
              className={styles.visuallyHidden}
              type="file"
              accept={photoAccept}
              multiple={max > 1}
              aria-label={t("사진 파일 선택", "Choose photo files")}
              onChange={add}
            />
          </label>
          <label className={styles.capture}>
            <Camera size={16} />
            <span>{t("카메라로 촬영", "Take a photo")}</span>
            <input
              className={styles.visuallyHidden}
              type="file"
              accept="image/*"
              capture="environment"
              aria-label={t("카메라로 촬영", "Take a photo")}
              onChange={add}
            />
          </label>
        </div>
      )}
      {problem && (
        <p className={styles.fieldError} role="alert">
          {problem}
        </p>
      )}
      {values.map((value, index) => (
        <div className={styles.photoEdit} key={value.key}>
          {value.file ? (
            <LocalPreview
              file={value.file}
              alt={
                value.altText ||
                t("선택한 사진 미리보기", "Selected photo preview")
              }
            />
          ) : (
            <PhotoView className={styles.photoPreview} photo={value.existing} />
          )}
          <label className={styles.field}>
            <span>
              {t("사진 설명", "Photo alternative text")} {index + 1}
            </span>
            <input
              required
              maxLength={200}
              value={value.altText}
              onChange={(event) =>
                change(
                  values.map((entry, position) =>
                    position === index
                      ? { ...entry, altText: event.target.value }
                      : entry,
                  ),
                )
              }
            />
          </label>
          <button
            className={styles.iconButton}
            type="button"
            aria-label={t("사진 제거", "Remove photo") + " " + (index + 1)}
            onClick={() =>
              change(values.filter((entry) => entry.key !== value.key))
            }
          >
            <X size={19} />
          </button>
        </div>
      ))}
      {required && values.length === 0 && (
        <p className={styles.muted}>
          {t(
            "물품 사진을 한 장 이상 첨부해 주세요.",
            "Attach at least one photo of the item.",
          )}
        </p>
      )}
    </div>
  );
}
