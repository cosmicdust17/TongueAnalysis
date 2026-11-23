import { defineStore } from "pinia";
import { ref } from "vue";
import type { User, Role, Session } from "@/types";
import { api } from "@/utils/request";
export function homeFor(role: Role) {
  return role === "knowledge_admin"
    ? "/subpackages/knowledge-admin/library"
    : role === "ops_admin"
      ? "/subpackages/ops-admin/overview"
      : "/pages/analysis/index";
}
export const useAuth = defineStore("auth", () => {
  const user = ref<User | null>(uni.getStorageSync("user") || null);
  function accept(session: Session) {
    uni.removeStorageSync("active_analysis");
    user.value = session.user;
    uni.setStorageSync("user", session.user);
    uni.setStorageSync("token", session.access_token);
  }
  function clear() {
    user.value = null;
    uni.removeStorageSync("token");
    uni.removeStorageSync("user");
    uni.removeStorageSync("active_analysis");
  }
  async function refresh() {
    user.value = await api<User>("/users/me");
    uni.setStorageSync("user", user.value);
  }
  async function logout() {
    try {
      await api("/auth/logout", "POST");
    } finally {
      clear();
      uni.reLaunch({ url: "/pages/login/index" });
    }
  }
  return { user, accept, clear, refresh, logout };
});
export function requireAuth(role?: Role): boolean {
  const auth = useAuth();
  if (!uni.getStorageSync("token") || !auth.user) {
    uni.reLaunch({ url: "/pages/login/index" });
    return false;
  }
  if (role && auth.user.role !== role) {
    uni.reLaunch({ url: homeFor(auth.user.role) });
    return false;
  }
  return true;
}
