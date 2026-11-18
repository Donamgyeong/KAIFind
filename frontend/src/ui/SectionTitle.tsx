import { ChevronLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { useSession } from "../api/session-context";
import styles from "./ui.module.css";

export default function SectionTitle({
  title,
  back,
}: {
  title: string;
  back?: string;
}) {
  const { t } = useSession();
  return (
    <div className={styles.pageTitle}>
      {back && (
        <Link
          to={back}
          className={styles.iconButton}
          aria-label={t("뒤로", "Back")}
        >
          <ChevronLeft size={24} />
        </Link>
      )}
      <h1>{title}</h1>
    </div>
  );
}
