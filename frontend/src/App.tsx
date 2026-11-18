import { useState } from "react";
import { Bell, House, LogIn, Plus, Search, UserRound } from "lucide-react";
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import type { ReactNode } from "react";
import SessionProvider from "./api/SessionProvider";
import { useSession } from "./api/session-context";
import Home from "./pages/Home";
import FoundDetail from "./pages/FoundDetail";
import FoundForm, { ChangeStorage, FoundCreated } from "./pages/FoundForm";
import MyFound from "./pages/MyFound";
import LostForm from "./pages/LostForm";
import LostReports, { LostDetail, Matches } from "./pages/LostReports";
import Conversations, { ConversationMessages } from "./pages/Messages";
import Login from "./pages/Login";
import { ErrorState, Loading } from "./ui/controls";
import ui from "./ui/ui.module.css";
import styles from "./shell.module.css";

export function RequireMember({
  children,
  admin = false,
}: {
  children: ReactNode;
  admin?: boolean;
}) {
  const session = useSession();
  const location = useLocation();
  if (session.checking) return <Loading />;
  if (session.sessionError)
    return (
      <ErrorState
        error={session.sessionError}
        retry={() => void session.refreshUser()}
      />
    );
  if (!session.user)
    return (
      <Navigate
        to={
          "/login?returnTo=" +
          encodeURIComponent(location.pathname + location.search)
        }
        replace
      />
    );
  if (admin && session.user.role !== "ADMIN")
    return (
      <p role="alert">
        {session.t(
          "관리자 권한이 필요합니다.",
          "Administrator access required.",
        )}
      </p>
    );
  return children;
}

function Shell() {
  const { t, lang, user, checking, revision, changeLanguage } = useSession();
  const [error, setError] = useState<unknown>();
  const [changing, setChanging] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const links = [
    { to: "/", label: t("홈", "Home"), Icon: House },
    { to: "/lost-reports", label: t("찾기", "Find"), Icon: Search },
    { to: "/me/found-items", label: t("등록", "Post"), Icon: Plus },
    { to: "/me", label: t("프로필", "Profile"), Icon: UserRound },
  ];
  const nav = links.map(({ to, label, Icon }) => (
    <NavLink
      key={to}
      to={to}
      end={to === "/" || to === "/me"}
      className={({ isActive }) =>
        isActive ||
        (to === "/" && location.pathname === "/found-items") ||
        (to === "/me/found-items" && location.pathname === "/found-items/new")
          ? styles.active
          : undefined
      }
    >
      <Icon size={22} strokeWidth={1.65} aria-hidden="true" />
      <span>{label}</span>
    </NavLink>
  ));
  const loginPath =
    "/login?returnTo=" +
    encodeURIComponent(location.pathname + location.search);

  return (
    <>
      <a href="#main" className={styles.skip}>
        {t("본문으로 이동", "Skip to content")}
      </a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link to="/" className={styles.brand}>
            KAIFind
          </Link>
          <nav
            className={styles.desktopNav}
            aria-label={t("주 메뉴", "Main navigation")}
          >
            {nav}
          </nav>
          <div className={styles.account}>
            <button
              type="button"
              className={styles.language}
              disabled={changing || checking}
              aria-label={lang === "ko" ? "Switch to English" : "한국어로 전환"}
              onClick={async () => {
                setChanging(true);
                setError(undefined);
                try {
                  await changeLanguage(lang === "ko" ? "en" : "ko");
                } catch (failure) {
                  setError(failure);
                } finally {
                  setChanging(false);
                }
              }}
            >
              <strong className={lang === "ko" ? styles.current : ""}>
                KO
              </strong>{" "}
              /{" "}
              <strong className={lang === "en" ? styles.current : ""}>
                EN
              </strong>
            </button>
            {!checking &&
              (user ? (
                <Link
                  className={ui.iconButton}
                  to="/me/notifications"
                  aria-label={t("알림", "Notifications")}
                >
                  <Bell size={22} />
                </Link>
              ) : (
                <Link
                  className={ui.iconButton}
                  to={loginPath}
                  aria-label={t("로그인", "Sign in")}
                >
                  <LogIn size={22} />
                </Link>
              ))}
          </div>
        </div>
      </header>
      <main id="main" className={styles.main} key={revision}>
        {error !== undefined && <ErrorState error={error} />}
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/found-items" element={<Home />} />
          <Route
            path="/lost-reports"
            element={
              <RequireMember>
                <LostReports />
              </RequireMember>
            }
          />
          <Route
            path="/lost-reports/new"
            element={
              <RequireMember>
                <LostForm />
              </RequireMember>
            }
          />
          <Route
            path="/lost-reports/:reportId"
            element={
              <RequireMember>
                <LostDetail />
              </RequireMember>
            }
          />
          <Route
            path="/lost-reports/:reportId/edit"
            element={
              <RequireMember>
                <LostForm />
              </RequireMember>
            }
          />
          <Route
            path="/lost-reports/:reportId/created"
            element={
              <RequireMember>
                <LostDetail created />
              </RequireMember>
            }
          />
          <Route
            path="/lost-reports/:reportId/matches"
            element={
              <RequireMember>
                <Matches />
              </RequireMember>
            }
          />
          <Route
            path="/conversations"
            element={
              <RequireMember>
                <Conversations />
              </RequireMember>
            }
          />
          <Route
            path="/conversations/:conversationId"
            element={
              <RequireMember>
                <ConversationMessages />
              </RequireMember>
            }
          />

          <Route path="/found-items/:itemId" element={<FoundDetail />} />
          <Route
            path="/found-items/new"
            element={
              <RequireMember>
                <FoundForm />
              </RequireMember>
            }
          />
          <Route
            path="/found-items/:itemId/edit"
            element={
              <RequireMember>
                <FoundForm />
              </RequireMember>
            }
          />
          <Route
            path="/found-items/:itemId/storage"
            element={
              <RequireMember>
                <ChangeStorage />
              </RequireMember>
            }
          />
          <Route
            path="/found-items/:itemId/created"
            element={
              <RequireMember>
                <FoundCreated />
              </RequireMember>
            }
          />
          <Route
            path="/me/found-items"
            element={
              <RequireMember>
                <MyFound />
              </RequireMember>
            }
          />

          <Route
            path="/login"
            element={
              <>
                <Home />
                <Login onClose={() => navigate("/", { replace: true })} />
              </>
            }
          />
          <Route
            path="*"
            element={
              <p className={ui.empty}>
                {t("페이지를 찾을 수 없어요.", "Page not found.")}{" "}
                <Link to="/">{t("홈으로", "Home")}</Link>
              </p>
            }
          />
        </Routes>
      </main>
      <nav
        className={styles.mobileNav}
        aria-label={t("주 메뉴", "Main navigation")}
      >
        {nav}
      </nav>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <Shell />
      </SessionProvider>
    </BrowserRouter>
  );
}
