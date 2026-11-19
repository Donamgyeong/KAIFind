export function signInPath(returnTo: string) {
  return "/login?returnTo=" + encodeURIComponent(returnTo);
}
