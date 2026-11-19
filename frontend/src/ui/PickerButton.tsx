import { ChevronDown } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useId } from "react";
import styles from "./ui.module.css";

export default function PickerButton({
  label,
  value,
  placeholder,
  open,
  onOpen,
  icon: Icon = ChevronDown,
}: {
  label?: string;
  value?: string;
  placeholder: string;
  open: boolean;
  onOpen: () => void;
  icon?: LucideIcon;
}) {
  const valueId = useId();
  return (
    <button
      type="button"
      className={styles.selectButton}
      aria-label={label}
      aria-describedby={label && value ? valueId : undefined}
      aria-haspopup="dialog"
      aria-expanded={open}
      data-placeholder={!value}
      onClick={onOpen}
    >
      <span id={valueId}>{value || placeholder}</span>
      <Icon size={16} strokeWidth={1.65} aria-hidden="true" />
    </button>
  );
}
