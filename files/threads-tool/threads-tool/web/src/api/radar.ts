import { request } from "./client";
import type { RadarPost, RadarSettings, RadarStats } from "../types";

export function getRadarSettings() {
  return request<RadarSettings>("/radar/settings");
}

export function updateRadarSettings(patch: Partial<RadarSettings>) {
  return request<RadarSettings>("/radar/settings", {
    method: "PUT",
    body: patch,
  });
}

export function collectRadar() {
  return request<{ status: string }>("/radar/collect", { method: "POST" });
}

export function listRadarPosts(overrides?: {
  min_likes?: number;
  max_age_hours?: number;
  min_score?: number;
  top_n?: number;
}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(overrides ?? {})) {
    if (v !== undefined && v !== null) qs.set(k, String(v));
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<RadarPost[]>(`/radar/posts${suffix}`);
}

export function getRadarStats() {
  return request<RadarStats>("/radar/stats");
}
