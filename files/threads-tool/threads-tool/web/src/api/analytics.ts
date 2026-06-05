import { request } from "./client";
import type { Post, Trend } from "../types";

export function pollAccount(accountId: string) {
  return request<{ status: string; account_id: string }>(
    `/analytics/accounts/${accountId}/poll`,
    { method: "POST" }
  );
}

export function searchKeyword(keyword: string) {
  return request<{ status: string; keyword: string }>("/analytics/trends/search", {
    method: "POST",
    body: { keyword },
  });
}

export function listTrends() {
  return request<Trend[]>("/analytics/trends");
}

export function listPosts() {
  return request<Post[]>("/analytics/posts");
}
