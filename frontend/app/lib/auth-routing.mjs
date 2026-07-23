export function routeForRole(role) {
  if (role === "CUSTOMER") return "/customer";
  if (role === "ANALYST") return "/analyst";
  return "/supervisor";
}
