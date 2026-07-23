export function routeForRole(role) {
  if (role === "CUSTOMER") return "/customer";
  if (role === "ANALYST") return "/analyst";
  if (role === "SUPERVISOR" || role === "ADMIN") return "/supervisor";
  return "/login";
}
