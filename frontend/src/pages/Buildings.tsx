import BuildingMap from "../ui/BuildingMap";
import { useSession } from "../api/session-context";
import { useBuildings } from "../api/useReferences";
import { ErrorState, Loading } from "../ui/controls";
import { buildingZones, localName } from "../ui/format";
import SectionTitle from "../ui/SectionTitle";
import ui from "../ui/ui.module.css";

export default function Buildings() {
  const { t, lang } = useSession();
  const result = useBuildings(true);
  return (
    <div className={ui.formPage}>
      <SectionTitle
        title={t("건물별 보관 물품", "Items by storage building")}
        back="/"
      />
      {result.loading && <Loading />}
      {result.error !== undefined && (
        <ErrorState error={result.error} retry={result.reload} />
      )}
      {result.data?.items.length === 0 && (
        <p className={ui.empty}>
          {t("표시할 건물이 없어요.", "No buildings to show.")}
        </p>
      )}
      {buildingZones(result.data?.items ?? [], t).map(
        ({ code, name, entries }) => (
          <details key={code} className={ui.panel + " " + ui.zone}>
            <summary>
              {name}{" "}
              <small>
                {entries.length}
                {t("개 건물", " buildings")}
              </small>
            </summary>
            <div className={ui.stack}>
              {entries.map((building) => (
                <div key={building.buildingId} className={ui.between}>
                  <div className={ui.field}>
                    <strong>
                      {building.code} · {localName(building, lang)}
                    </strong>
                    <small className={ui.muted}>
                      {t("보관 중", "In storage")} ·{" "}
                      {(building.postedCount ?? 0).toLocaleString(lang)}
                    </small>
                  </div>
                  <BuildingMap building={building} iconOnly />
                </div>
              ))}
            </div>
          </details>
        ),
      )}
    </div>
  );
}
