import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProxy,
  deleteProxy,
  listProxies,
  testProxy,
  updateProxy,
} from "../api/proxies";
import { ApiError } from "../api/client";
import type { Proxy, ProxyInput, ProxyProtocol } from "../types";

const EMPTY: ProxyInput = {
  label: "",
  protocol: "http",
  host: "",
  port: 8080,
  username: "",
  password: "",
  active: true,
};

const PROTOCOLS: ProxyProtocol[] = ["http", "https", "socks5"];

export default function ProxiesPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState<ProxyInput>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const { data: proxies, isLoading } = useQuery({
    queryKey: ["proxies"],
    queryFn: listProxies,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["proxies"] });

  const create = useMutation({
    mutationFn: (input: ProxyInput) => createProxy(input),
    onSuccess: () => {
      setForm(EMPTY);
      invalidate();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không tạo được proxy"),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    create.mutate({
      ...form,
      username: form.username || undefined,
      password: form.password || undefined,
    });
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Proxy</h1>
        <p className="mt-1 text-sm text-gray-500">
          Định tuyến request ra Threads/tải media qua proxy. Account có thể gán
          proxy cố định; account chưa gán dùng chung pool (các proxy “active”).
        </p>
      </div>

      <section className="card">
        <h2 className="mb-3 text-lg font-semibold">Thêm proxy</h2>
        <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2">
          <input
            className="input"
            placeholder="Nhãn (vd: US-1)"
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            required
          />
          <select
            className="input"
            value={form.protocol}
            onChange={(e) =>
              setForm({ ...form, protocol: e.target.value as ProxyProtocol })
            }
          >
            {PROTOCOLS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <input
            className="input"
            placeholder="Host / IP"
            value={form.host}
            onChange={(e) => setForm({ ...form, host: e.target.value })}
            required
          />
          <input
            className="input"
            type="number"
            placeholder="Port"
            value={form.port}
            min={1}
            max={65535}
            onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
            required
          />
          <input
            className="input"
            placeholder="Username (tùy chọn)"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
          <input
            className="input"
            type="password"
            placeholder="Password (tùy chọn)"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm({ ...form, active: e.target.checked })}
            />
            Tham gia pool xoay vòng
          </label>
          <div className="sm:col-span-2">
            <button className="btn-primary" disabled={create.isPending}>
              {create.isPending ? "Đang lưu…" : "Thêm proxy"}
            </button>
          </div>
        </form>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Danh sách proxy</h2>
        {isLoading ? (
          <p className="text-sm text-gray-500">Đang tải…</p>
        ) : (proxies?.length ?? 0) === 0 ? (
          <p className="text-sm text-gray-500">Chưa có proxy nào.</p>
        ) : (
          <div className="space-y-3">
            {proxies!.map((p) => (
              <ProxyRow key={p.id} proxy={p} onChanged={invalidate} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ProxyRow({ proxy, onChanged }: { proxy: Proxy; onChanged: () => void }) {
  const [msg, setMsg] = useState<string | null>(null);

  const test = useMutation({
    mutationFn: () => testProxy(proxy.id),
    onSuccess: (res) => {
      setMsg(res.ok ? `OK · IP ${res.ip ?? "?"}` : `Lỗi: ${res.error ?? "?"}`);
      onChanged();
    },
  });

  const toggle = useMutation({
    mutationFn: () => updateProxy(proxy.id, { active: !proxy.active }),
    onSuccess: onChanged,
  });

  const remove = useMutation({
    mutationFn: () => deleteProxy(proxy.id),
    onSuccess: onChanged,
  });

  const lc = proxy.last_check;

  return (
    <div className="card flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{proxy.label}</span>
          <span className="badge bg-gray-100 text-gray-600">{proxy.protocol}</span>
          <span
            className={`badge ${
              proxy.active
                ? "bg-green-100 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {proxy.active ? "pool: bật" : "pool: tắt"}
          </span>
          {lc && (
            <span
              className={`badge ${
                lc.ok ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"
              }`}
            >
              {lc.ok ? `test OK${lc.ip ? ` · ${lc.ip}` : ""}` : "test lỗi"}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-gray-600">
          {proxy.username ? `${proxy.username}@` : ""}
          {proxy.host}:{proxy.port}
        </p>
        {msg && <p className="mt-1 text-xs text-gray-500">{msg}</p>}
      </div>
      <div className="flex shrink-0 gap-2">
        <button
          className="btn-secondary"
          onClick={() => test.mutate()}
          disabled={test.isPending}
        >
          {test.isPending ? "Đang test…" : "Test"}
        </button>
        <button
          className="btn-secondary"
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
        >
          {proxy.active ? "Tắt pool" : "Bật pool"}
        </button>
        <button
          className="btn-secondary text-red-600"
          onClick={() => {
            if (confirm(`Xóa proxy "${proxy.label}"?`)) remove.mutate();
          }}
          disabled={remove.isPending}
        >
          Xóa
        </button>
      </div>
    </div>
  );
}
