import { ChevronRight } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../api/session-context";
import type { MockAccount } from "../api/types";
import { useAction } from "../api/useAction";
import { useRemote } from "../api/useRemote";
import { Dialog, ErrorState, Loading } from "../ui/controls";
import { affiliationLabel } from "../ui/format";
import styles from "./profile.module.css";

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
  const action = useAction();

  return (
    <Dialog
      title={t("KAIFind 로그인", "Sign in to KAIFind")}
      className={styles.loginDialog}
      close={() => {
        if (!action.busy) onClose();
      }}
    >
      {accounts.loading && <Loading />}
      {accounts.error !== undefined && (
        <ErrorState error={accounts.error} retry={accounts.reload} />
      )}
      <div className={styles.loginAccounts} aria-busy={action.busy}>
        {accounts.data?.accounts.map((account) => (
          <button
            key={account.mockAccountId}
            type="button"
            className={styles.loginAccount}
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                await signIn(account.mockAccountId);
                navigate(destination(params.get("returnTo")), {
                  replace: true,
                });
              })
            }
          >
            <span className={styles.accountAvatar} aria-hidden="true">
              {
                Array.from(
                  account.displayName.replace(/^(테스트|test)\s+/i, ""),
                )[0]
              }
            </span>
            <span className={styles.accountIdentity}>
              <strong>{account.displayName}</strong>
              <small>
                {account.role === "ADMIN"
                  ? t("관리자", "Administrator")
                  : affiliationLabel(account.affiliation, t)}
              </small>
            </span>
            <ChevronRight size={20} strokeWidth={1.65} aria-hidden="true" />
          </button>
        ))}
      </div>
      {action.error !== undefined && <ErrorState error={action.error} />}
      {accounts.data?.accounts.length ? (
        <p className={styles.loginNote}>
          {t(
            "시연용 가상 프로필입니다.",
            "These profiles are for demonstration.",
          )}
        </p>
      ) : null}
    </Dialog>
  );
}
