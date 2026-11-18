import { campusBuildings, campusCategories } from "./campus-buildings.mjs";

const base = new URL(
  process.env.KAIFIND_SEED_ORIGIN ?? "https://localhost:3000",
);
if (base.protocol !== "https:")
  throw new Error("KAIFIND_SEED_ORIGIN must use HTTPS.");

let cookie;
let csrfToken;

async function request(path, method = "GET", body) {
  const headers = new Headers({ "Accept-Language": "en" });
  if (cookie) headers.set("Cookie", cookie);
  if (method !== "GET") {
    headers.set("Origin", base.origin);
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  if (body) headers.set("Content-Type", "application/json");
  const response = await fetch(new URL("/api/v1" + path, base), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    redirect: "error",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      method +
        " " +
        path +
        " failed (" +
        response.status +
        " " +
        (error.code ?? "") +
        ").",
    );
  }
  const newCookie = response.headers
    .getSetCookie()
    .find((value) => value.startsWith("KAIFIND_SESSION="));
  if (newCookie) cookie = newCookie.split(";", 1)[0];
  if (response.status !== 204) return response.json();
}

async function insertMissing(path, entries, identify) {
  const existing = new Map();
  let page = 0;
  while (true) {
    const result = await request(path + "?size=100&page=" + page);
    for (const entry of result.items) existing.set(identify(entry), entry);
    if (++page >= result.totalPages) break;
  }
  let created = 0;
  for (const entry of entries) {
    if (!existing.has(identify(entry))) {
      await request(path, "POST", entry);
      created += 1;
    }
  }
  console.log(
    path +
      " · " +
      created +
      " added, " +
      (entries.length - created) +
      " already registered",
  );
  const review = entries.filter((entry) => {
    const value = existing.get(identify(entry));
    return (
      value &&
      (!value.active ||
        (entry.sensitive !== undefined && value.sensitive !== entry.sensitive))
    );
  });
  if (review.length)
    console.log(
      "Review existing settings in Admin · " + review.map(identify).join(", "),
    );
}

const accountId = process.env.KAIFIND_SEED_ACCOUNT ?? "admin-01";
const result = await request("/auth/csrf");
csrfToken = result.csrfToken;
const login = await request("/auth/mock/login", "POST", {
  mockAccountId: accountId,
});
csrfToken = login.csrfToken;
try {
  if (login.user.role !== "ADMIN")
    throw new Error("The demo account must have the ADMIN role.");
  await insertMissing("/admin/buildings", campusBuildings, (entry) =>
    entry.code.toUpperCase(),
  );
  await insertMissing(
    "/admin/categories",
    campusCategories,
    (entry) => entry.nameKo,
  );
} finally {
  await request("/auth/logout", "POST");
}
