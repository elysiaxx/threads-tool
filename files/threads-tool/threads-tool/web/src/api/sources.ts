import { request } from "./client";
import type { Source } from "../types";

export function listSources() {
  return request<Source[]>("/sources");
}

export function createSource(sourceUrl: string) {
  return request<Source>("/sources", {
    method: "POST",
    body: { source_url: sourceUrl },
  });
}

export function getSource(id: string) {
  return request<Source>(`/sources/${id}`);
}
