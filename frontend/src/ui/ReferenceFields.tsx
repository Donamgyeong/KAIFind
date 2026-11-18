import { useSession } from "../api/session-context";
import type { Category } from "../api/types";
import { localName } from "./format";

export function CategorySelect({
  categories,
  value,
  change,
  label,
}: {
  categories: Category[];
  value: string;
  change: (value: string) => void;
  label: string;
}) {
  const { t, lang } = useSession();
  return (
    <select
      aria-label={label}
      value={value}
      required
      onChange={(event) => change(event.target.value)}
    >
      <option value="" disabled>
        {t("물품 분류를 선택해 주세요", "Select a category")}
      </option>
      {categories.map((category) => (
        <option value={category.categoryId} key={category.categoryId}>
          {localName(category, lang)}
        </option>
      ))}
    </select>
  );
}
