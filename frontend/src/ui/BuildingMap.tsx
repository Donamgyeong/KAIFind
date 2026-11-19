import { useState } from "react";
import { MapPin } from "lucide-react";
import { useSession } from "../api/session-context";
import type { Building } from "../api/types";
import { Dialog } from "./controls";
import { localName } from "./format";
import ui from "./ui.module.css";
import styles from "./building-map.module.css";

export default function BuildingMap({
  building,
  iconOnly = false,
}: {
  building: Building;
  iconOnly?: boolean;
}) {
  const { t, lang } = useSession();
  const [open, setOpen] = useState(false);
  const title = t("건물 위치", "Building location");
  const label = t("지도에서 보기", "View on map");
  const map = new URL("https://maps.google.com/maps");
  map.search = new URLSearchParams({
    q: "한국과학기술원 " + building.nameKo,
    output: "embed",
    hl: lang,
  }).toString();

  return (
    <>
      <button
        type="button"
        className={iconOnly ? ui.iconButton : styles.mapLink}
        aria-label={building.code + " " + label}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <MapPin size={16} strokeWidth={1.65} aria-hidden="true" />
        {!iconOnly && label}
      </button>
      {open && (
        <Dialog
          title={title}
          close={() => setOpen(false)}
          className={styles.mapDialog}
        >
          <div className={styles.buildingName}>
            <b>KAIST · {building.code}</b>
            <strong>{localName(building, lang)}</strong>
          </div>
          <iframe
            className={styles.mapFrame}
            src={map.href}
            title={title + " · " + building.code}
            referrerPolicy="no-referrer"
            allowFullScreen
          />
          <p className={styles.mapSource}>
            {t("지도 데이터 · Google 지도", "Map data · Google Maps")}
          </p>
          <button
            type="button"
            className={ui.secondary + " " + ui.full}
            onClick={() => setOpen(false)}
          >
            {t("확인했어요", "Done")}
          </button>
        </Dialog>
      )}
    </>
  );
}
