import { request } from "./client";
import type { Job, PublishInput } from "../types";

export function listJobs() {
  return request<Job[]>("/publish");
}

export function createJob(input: PublishInput) {
  return request<Job>("/publish", { method: "POST", body: input });
}

export function retryJob(id: string) {
  return request<Job>(`/publish/${id}/retry`, { method: "POST" });
}
