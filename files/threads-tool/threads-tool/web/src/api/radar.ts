import { request } from "./client";
import type {
  RadarPost,
  RadarDocIdDiscovery,
  RadarSession,
  RadarSessionTest,
  RadarSettings,
  RadarStats,
  RadarStatus,
  RadarWatchItem,
  TargetKind,
  TrackTarget,
} from "../types";

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

export function getWatchlist() {
  return request<RadarWatchItem[]>("/radar/watchlist");
}

export function getRadarStatus() {
  return request<RadarStatus>("/radar/status");
}

export function getSession() {
  return request<RadarSession>("/radar/session");
}

export function saveSession(cookie: string) {
  return request<RadarSession>("/radar/session", {
    method: "PUT",
    body: { cookie },
  });
}

export function deleteSession() {
  return request<void>("/radar/session", { method: "DELETE" });
}

export function testSession() {
  return request<RadarSessionTest>("/radar/session/test", { method: "POST" });
}

export function discoverSessionDocId() {
  return request<RadarDocIdDiscovery>("/radar/session/discover-doc-id", {
    method: "POST",
  });
}

export function listTargets() {
  return request<TrackTarget[]>("/radar/targets");
}

export function addTarget(kind: TargetKind, value: string) {
  return request<TrackTarget>("/radar/targets", {
    method: "POST",
    body: { kind, value },
  });
}

export function removeTarget(id: string) {
  return request<void>(`/radar/targets/${id}`, { method: "DELETE" });
}
