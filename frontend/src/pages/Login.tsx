import { useState } from "react";
import { LogIn } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { MockAccount } from "../api/types";
import { useRemote } from "../api/useRemote";
import { Dialog, ErrorState, Loading } from "../ui/controls";
import ui from "../ui/ui.module.css";

function destination(path: string | null) {
  return path?.startsWith("/") &&
    !path.startsWith("//") &&
    !path.includes("\\") &&
    new URL(path, location.origin).pathname !== "/login"
    ? path
    : "/";
}

export default function Login({ onClose }: { onClose: () => void }) {
  const { t, signIn } = useSession();
  const accounts = useRemote<{ accounts: MockAccount[] }>(
    "/auth/mock/accounts",
    true,
  );
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title={t("KAIFind 로그인", "Sign in to KAIFind")} close={onClose}>
      <form
        className={ui.stack}
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy || !selected) return;
          setBusy(true);
          setError(undefined);
          try {
            await signIn(selected);
            navigate(destination(params.get("returnTo")), { replace: true });
          } catch (failure) {
            setError(failure);
          } finally {
            setBusy(false);
          }
        }}
      >
        <p className={ui.muted}>
          {t(
            "시연용 KAIST 계정을 선택해 주세요.",
            "Choose a KAIST demo account.",
          )}
        </p>
        {accounts.loading && <Loading />}
        {accounts.error !== undefined && (
          <ErrorState error={accounts.error} retry={accounts.reload} />
        )}
        {accounts.data?.accounts.map((account) => (
          <label
            key={account.mockAccountId}
            className={ui.panel + " " + ui.row}
          >
            <input
              type="radio"
              name="account"
              value={account.mockAccountId}
              checked={selected === account.mockAccountId}
              onChange={() => setSelected(account.mockAccountId)}
              disabled={busy}
            />
            {account.displayName}
            {account.role === "ADMIN" && (
              <span className={ui.badge}>{t("관리자", "Admin")}</span>
            )}
          </label>
        ))}
        {error !== undefined && <ErrorState error={error} />}
        <button
          type="submit"
          className={ui.primary}
          disabled={!selected || busy}
        >
          <LogIn size={18} />
          {t("로그인", "Sign in")}
        </button>
      </form>
    </Dialog>
  );
}
