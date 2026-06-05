import { request } from "./client";
import type { Account, Proxy, ProxyCheck, ProxyInput } from "../types";

export function listProxies() {
  return request<Proxy[]>("/proxies");
}

export function createProxy(input: ProxyInput) {
  return request<Proxy>("/proxies", { method: "POST", body: input });
}

export function updateProxy(id: string, patch: Partial<ProxyInput>) {
  return request<Proxy>(`/proxies/${id}`, { method: "PATCH", body: patch });
}

export function deleteProxy(id: string) {
  return request<void>(`/proxies/${id}`, { method: "DELETE" });
}

export function testProxy(id: string) {
  return request<ProxyCheck>(`/proxies/${id}/test`, { method: "POST" });
}

// Gán/gỡ proxy cho 1 account (proxy_id = null để gỡ).
export function assignProxy(accountId: string, proxyId: string | null) {
  return request<Account>(`/accounts/${accountId}/proxy`, {
    method: "PATCH",
    body: { proxy_id: proxyId },
  });
}
