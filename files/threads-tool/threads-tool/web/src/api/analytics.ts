import { request } from "./client";
import type { MetricPoint, Post, Trend } from "../types";

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

export function listMetrics(postId?: string, hours = 168) {
  const qs = new URLSearchParams({ hours: String(hours) });
  if (postId) qs.set("post_id", postId);
  return request<MetricPoint[]>(`/analytics/metrics?${qs.toString()}`);
}
