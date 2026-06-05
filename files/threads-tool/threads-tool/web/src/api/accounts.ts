import { request } from "./client";
import type { Account } from "../types";

export function listAccounts() {
  return request<Account[]>("/accounts");
}

export function trackAccount(username: string, platform = "threads") {
  return request<Account>("/accounts/track", {
    method: "POST",
    body: { username, platform },
  });
}

// Lấy authorize URL (JSON, có auth) rồi điều hướng cả trang sang Meta. Không
// dùng endpoint redirect /start trực tiếp vì navigation không mang Bearer header.
export async function getAuthorizeUrl(platform = "threads") {
  return request<{ url: string }>(`/accounts/oauth/${platform}/authorize-url`);
}
