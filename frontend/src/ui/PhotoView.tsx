import { useEffect, useRef, useState } from "react";
import { Image as ImageIcon, LockKeyhole } from "lucide-react";
import { ApiError } from "../api/client";
import { useSession } from "../api/session-context";
import type { Photo } from "../api/types";
import styles from "./ui.module.css";

export default function PhotoView({
  photo,
  locked,
  className = "",
}: {
  photo?: Photo;
  locked?: boolean;
  className?: string;
}) {
  const { api, user, revision, t } = useSession();
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [image, setImage] = useState<{ key: string; src: string }>();
  const photoId =
    photo && (!photo.accessRequiresLogin || user) ? photo.photoId : undefined;
  const key = photoId + ":" + revision;

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "100px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || !photoId) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    const signal = controller.signal;
    async function load(retry = true): Promise<void> {
      const link = await api.request<{ url: string }>(
        "/photos/" + photoId + "/access-url",
        { method: "POST", signal },
      );
      const url = new URL(link.url, location.origin);
      if (!url.pathname.startsWith("/api/v1/photo-access/"))
        throw new Error("Unexpected photo URL");
      const response = await fetch(url.pathname + url.search, {
        credentials: "same-origin",
        cache: "no-store",
        signal,
        referrerPolicy: "no-referrer",
      });
      if (response.status === 410 && retry) return load(false);
      if (!response.ok)
        throw new ApiError(response.status, "PHOTO_UNAVAILABLE", "", []);
      const blob = await response.blob();
      if (signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setImage({ key, src: objectUrl });
    }
    void load().catch(() => {});
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, key, photoId, visible]);

  return (
    <div ref={host} className={styles.photo + " " + className}>
      {photoId && image?.key === key ? (
        <img src={image.src} alt={photo?.altText ?? ""} />
      ) : locked ? (
        <LockKeyhole
          aria-label={t("로그인 후 사진 보기", "Sign in to view photo")}
          size={31}
        />
      ) : (
        <ImageIcon aria-label={t("사진 없음", "Photo unavailable")} size={28} />
      )}
    </div>
  );
}
