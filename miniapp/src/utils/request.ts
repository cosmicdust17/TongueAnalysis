import { beijingClock } from "./beijing-date";
import type { Uploaded } from "@/types";
export const BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");
export function authHeader() {
  return { Authorization: `Bearer ${uni.getStorageSync("token") || ""}` };
}
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
  }
}

function errorMessage(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "输入内容格式不正确，请检查后重试";
  if (detail && typeof detail === "object" && "message" in detail)
    return String(detail.message);
  if (status === 403) return "没有访问权限";
  if (status === 404) return "记录不存在";
  if (status === 503) return "业务数据库暂时不可用，请稍后重试";
  return "请求失败，请稍后重试";
}
function rejected(status: number, data: unknown) {
  if (status === 401) {
    uni.removeStorageSync("token");
    uni.removeStorageSync("user");
    uni.reLaunch({ url: "/pages/login/index" });
  }
  const detail = (data as { detail?: { code?: unknown } })?.detail;
  const code = typeof detail?.code === "string" ? detail.code : undefined;
  return new ApiError(errorMessage(data, status), status, code);
}
export function api<T>(
  path: string,
  method: "GET" | "POST" | "PUT" | "DELETE" = "GET",
  data?: unknown,
): Promise<T> {
  return new Promise((resolve, reject) =>
    uni.request({
      url: BASE_URL + "/api/v1" + path,
      method,
      data: data as UniApp.RequestOptions["data"],
      header: { ...authHeader(), "Content-Type": "application/json" },
      timeout: 20000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300)
          resolve(res.data as T);
        else reject(rejected(res.statusCode, res.data));
      },
      fail: () =>
        reject(
          new Error("无法连接后端，请检查服务地址、局域网和开发者工具设置"),
        ),
    }),
  );
}
export function upload(filePath: string, purpose = "image"): Promise<Uploaded> {
  return new Promise((resolve, reject) =>
    uni.uploadFile({
      url: BASE_URL + "/api/v1/uploads?purpose=" + purpose,
      filePath,
      name: "file",
      header: authHeader(),
      timeout: 60000,
      success: (res) => {
        try {
          const data = JSON.parse(res.data);
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(data);
          else reject(rejected(res.statusCode, data));
        } catch {
          reject(new Error("上传响应格式错误"));
        }
      },
      fail: () => reject(new Error("上传失败，请检查网络后重试")),
    }),
  );
}
export function download(path: string): Promise<string> {
  return new Promise((resolve, reject) =>
    uni.downloadFile({
      url: BASE_URL + "/api/v1" + path,
      header: authHeader(),
      timeout: 30000,
      success: (res) => {
        if (res.statusCode === 200) resolve(res.tempFilePath);
        else
          reject(
            new Error(
              res.statusCode === 401
                ? "登录已失效，请重新登录"
                : "文件下载失败",
            ),
          );
      },
      fail: () => reject(new Error("文件下载失败，请检查网络")),
    }),
  );
}
export function toastError(error: unknown) {
  uni.showToast({
    title: error instanceof Error ? error.message : "操作失败，请重试",
    icon: "none",
    duration: 3000,
  });
}
export function dateText(value: string, short = false) {
  const c = beijingClock(value);
  if (Number.isNaN(c.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  const day = pad(c.getUTCMonth() + 1) + "/" + pad(c.getUTCDate());
  return (
    (short ? "" : c.getUTCFullYear() + "/") +
    day +
    " " +
    pad(c.getUTCHours()) +
    ":" +
    pad(c.getUTCMinutes())
  );
}
export function query(values: Record<string, string | number>) {
  return (
    "?" +
    Object.entries(values)
      .map(
        ([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(String(v)),
      )
      .join("&")
  );
}
export function confirmAction(content: string): Promise<boolean> {
  return new Promise((resolve) =>
    uni.showModal({
      title: "确认操作",
      confirmColor: "#315D49",
      content,
      success: (r) => resolve(r.confirm),
      fail: () => resolve(false),
    }),
  );
}
