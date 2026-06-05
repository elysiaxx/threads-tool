import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { listPosts, listTrends, searchKeyword } from "../api/analytics";
import { ApiError } from "../api/client";
import type { Post, Trend } from "../types";

export default function AnalyticsPage() {
  const qc = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: posts } = useQuery({ queryKey: ["posts"], queryFn: listPosts });
  const { data: trends } = useQuery({ queryKey: ["trends"], queryFn: listTrends });

  const search = useMutation({
    mutationFn: (k: string) => searchKeyword(k),
    onSuccess: () => {
      setKeyword("");
      setNotice("Đã xếp hàng tìm kiếm. Kết quả sẽ xuất hiện ở mục Trends sau ít phút.");
      qc.invalidateQueries({ queryKey: ["trends"] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không tìm được"),
  });

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (keyword.trim()) search.mutate(keyword.trim());
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <h1 className="text-2xl font-bold">Analytics</h1>

      <StatCards posts={posts} trends={trends} />

      <div className="grid gap-6 lg:grid-cols-2">
        <PostsByTypeChart posts={posts} />
        <TrendsChart trends={trends} />
      </div>

      <section className="card">
        <h2 className="mb-3 text-lg font-semibold">Tìm kiếm từ khoá</h2>
        <form onSubmit={onSearch} className="flex gap-2">
          <input
            className="input max-w-sm"
            placeholder="ví dụ: ai, marketing…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <button className="btn-primary" disabled={search.isPending}>
            {search.isPending ? "Đang gửi…" : "Tìm"}
          </button>
        </form>
        {notice && <p className="mt-2 text-sm text-green-700">{notice}</p>}
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <p className="mt-2 text-xs text-gray-400">
          Lưu ý: keyword search của Threads bị giới hạn tần suất — kết quả được lưu
          vào Trends để cache.
        </p>
      </section>

      <TrendsTable trends={trends} />
      <RecentPosts posts={posts} />
    </div>
  );
}

function StatCards({ posts, trends }: { posts?: Post[]; trends?: Trend[] }) {
  const cards = [
    { label: "Tổng số post", value: posts?.length ?? 0 },
    { label: "Snapshot trends", value: trends?.length ?? 0 },
    {
      label: "Từ khoá theo dõi",
      value: new Set((trends ?? []).map((t) => t.keyword)).size,
    },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {cards.map((c) => (
        <div key={c.label} className="card">
          <div className="text-3xl font-bold">{c.value}</div>
          <div className="mt-1 text-sm text-gray-500">{c.label}</div>
        </div>
      ))}
    </div>
  );
}

function PostsByTypeChart({ posts }: { posts?: Post[] }) {
  const data = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of posts ?? []) {
      const key = p.media_type || "UNKNOWN";
      counts[key] = (counts[key] || 0) + 1;
    }
    return Object.entries(counts).map(([type, count]) => ({ type, count }));
  }, [posts]);

  return (
    <div className="card">
      <h2 className="mb-3 text-lg font-semibold">Post theo loại media</h2>
      {data.length === 0 ? (
        <Empty />
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="type" fontSize={12} />
            <YAxis allowDecimals={false} fontSize={12} />
            <Tooltip />
            <Bar dataKey="count" fill="#000000" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function TrendsChart({ trends }: { trends?: Trend[] }) {
  const data = useMemo(
    () =>
      [...(trends ?? [])]
        .reverse()
        .map((t) => ({
          ts: new Date(t.ts).toLocaleDateString(),
          count: t.result_count,
        })),
    [trends]
  );

  return (
    <div className="card">
      <h2 className="mb-3 text-lg font-semibold">Kết quả từ khoá theo thời gian</h2>
      {data.length === 0 ? (
        <Empty />
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="ts" fontSize={12} />
            <YAxis allowDecimals={false} fontSize={12} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="count"
              stroke="#1d9bf0"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function TrendsTable({ trends }: { trends?: Trend[] }) {
  if (!trends || trends.length === 0) return null;
  return (
    <section className="card">
      <h2 className="mb-3 text-lg font-semibold">Trends gần đây</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-gray-500">
            <tr className="border-b">
              <th className="py-2 pr-4">Từ khoá</th>
              <th className="py-2 pr-4">Kết quả</th>
              <th className="py-2">Thời điểm</th>
            </tr>
          </thead>
          <tbody>
            {trends.slice(0, 15).map((t) => (
              <tr key={t.id} className="border-b last:border-0">
                <td className="py-2 pr-4 font-medium">{t.keyword}</td>
                <td className="py-2 pr-4">{t.result_count}</td>
                <td className="py-2 text-gray-500">
                  {new Date(t.ts).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RecentPosts({ posts }: { posts?: Post[] }) {
  if (!posts || posts.length === 0) return null;
  return (
    <section className="card">
      <h2 className="mb-3 text-lg font-semibold">Post gần đây</h2>
      <ul className="divide-y">
        {posts.slice(0, 10).map((p) => (
          <li key={p.id} className="py-3">
            <p className="line-clamp-2 text-sm text-gray-800">
              {p.text || <span className="text-gray-400">(không có nội dung)</span>}
            </p>
            <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
              {p.media_type && <span>{p.media_type}</span>}
              {p.published_at && (
                <span>{new Date(p.published_at).toLocaleString()}</span>
              )}
              {p.permalink && (
                <a
                  href={p.permalink}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand-accent underline"
                >
                  Mở
                </a>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Empty() {
  return (
    <div className="flex h-[240px] items-center justify-center text-sm text-gray-400">
      Chưa có dữ liệu
    </div>
  );
}
