import { useEffect, useState } from "react";
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
import {
  collectRadar,
  getRadarSettings,
  getRadarStats,
  listRadarPosts,
  updateRadarSettings,
} from "../api/radar";
import { ApiError } from "../api/client";
import type { RadarPost, RadarSettings, RadarStats } from "../types";

export default function TrendRadarPage() {
  const qc = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: settings } = useQuery({
    queryKey: ["radar-settings"],
    queryFn: getRadarSettings,
  });
  const { data: stats } = useQuery({
    queryKey: ["radar-stats"],
    queryFn: getRadarStats,
  });
  const { data: posts } = useQuery({
    queryKey: ["radar-posts"],
    queryFn: () => listRadarPosts(),
  });

  const collect = useMutation({
    mutationFn: collectRadar,
    onSuccess: () => {
      setError(null);
      setNotice(
        "Đã xếp hàng thu thập watchlist. Số liệu sẽ cập nhật sau ít phút — bấm Làm mới."
      );
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không thu thập được"),
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ["radar-stats"] });
    qc.invalidateQueries({ queryKey: ["radar-posts"] });
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Xu hướng (Trend Radar)</h1>
          <p className="mt-1 text-sm text-gray-500">
            Theo dõi nội dung public của watchlist và phát hiện bài đang lên xu hướng.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={refresh}>
            Làm mới
          </button>
          <button
            className="btn-primary"
            onClick={() => collect.mutate()}
            disabled={collect.isPending}
          >
            {collect.isPending ? "Đang gửi…" : "Thu thập ngay"}
          </button>
        </div>
      </div>

      {notice && <p className="text-sm text-green-700">{notice}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <StatCards stats={stats} />

      <SettingsPanel
        settings={settings}
        onSaved={() => {
          setNotice("Đã lưu ngưỡng. Bảng xếp hạng được tính lại theo ngưỡng mới.");
          setError(null);
          refresh();
        }}
        onError={(m) => setError(m)}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <AccountChart stats={stats} />
        <MediaTypeChart stats={stats} />
      </div>

      <TimelineChart stats={stats} />

      <TrendingTable posts={posts} />
    </div>
  );
}

function StatCards({ stats }: { stats?: RadarStats }) {
  const cards = [
    { label: "Bài trending", value: stats?.trending_posts ?? 0 },
    { label: "Bài theo dõi", value: stats?.tracked_posts ?? 0 },
    { label: "Tài khoản nguồn", value: stats?.source_accounts ?? 0 },
    { label: "Engagement TB", value: stats?.avg_engagement ?? 0 },
  ];
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="card">
            <div className="text-3xl font-bold">{c.value}</div>
            <div className="mt-1 text-sm text-gray-500">{c.label}</div>
          </div>
        ))}
      </div>
      {stats?.last_collected_at && (
        <p className="mt-2 text-xs text-gray-400">
          Lần thu thập gần nhất: {new Date(stats.last_collected_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}

const FIELDS: { key: keyof RadarSettings; label: string; step?: number }[] = [
  { key: "min_likes", label: "Like tối thiểu" },
  { key: "min_engagement", label: "Engagement tối thiểu" },
  { key: "max_age_hours", label: "Tuổi tối đa (giờ)" },
  { key: "min_score", label: "Score tối thiểu", step: 0.1 },
  { key: "reply_weight", label: "Trọng số reply", step: 0.5 },
  { key: "quote_weight", label: "Trọng số quote", step: 0.5 },
  { key: "gravity", label: "Gravity (độ mới)", step: 0.1 },
  { key: "top_n", label: "Số bài tối đa" },
];

function SettingsPanel({
  settings,
  onSaved,
  onError,
}: {
  settings?: RadarSettings;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const [form, setForm] = useState<RadarSettings | null>(null);
  useEffect(() => {
    if (settings) setForm(settings);
  }, [settings]);

  const save = useMutation({
    mutationFn: (patch: RadarSettings) => updateRadarSettings(patch),
    onSuccess: onSaved,
    onError: (e) =>
      onError(e instanceof ApiError ? e.message : "Không lưu được ngưỡng"),
  });

  if (!form) return null;

  return (
    <section className="card">
      <h2 className="mb-1 text-lg font-semibold">Ngưỡng xác định xu hướng</h2>
      <p className="mb-4 text-xs text-gray-500">
        score = engagement / (tuổi_giờ + 2)<sup>gravity</sup>; engagement = like +
        reply·trọng_số + quote·trọng_số. Gravity cao ⇒ ưu tiên bài mới.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {FIELDS.map((f) => (
          <label key={f.key} className="block text-sm">
            <span className="mb-1 block text-gray-600">{f.label}</span>
            <input
              type="number"
              step={f.step ?? 1}
              className="input"
              value={form[f.key]}
              onChange={(e) =>
                setForm({ ...form, [f.key]: Number(e.target.value) })
              }
            />
          </label>
        ))}
      </div>
      <div className="mt-4">
        <button
          className="btn-primary"
          onClick={() => save.mutate(form)}
          disabled={save.isPending}
        >
          {save.isPending ? "Đang lưu…" : "Lưu ngưỡng"}
        </button>
      </div>
    </section>
  );
}

function AccountChart({ stats }: { stats?: RadarStats }) {
  const data = (stats?.by_account ?? []).map((b) => ({
    name: b.label,
    count: b.count,
  }));
  return (
    <div className="card">
      <h2 className="mb-3 text-lg font-semibold">Top tài khoản nguồn</h2>
      {data.length === 0 ? (
        <Empty />
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} layout="vertical" margin={{ left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" allowDecimals={false} fontSize={12} />
            <YAxis type="category" dataKey="name" width={90} fontSize={11} />
            <Tooltip />
            <Bar dataKey="count" fill="#1d9bf0" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function MediaTypeChart({ stats }: { stats?: RadarStats }) {
  const data = (stats?.by_media_type ?? []).map((b) => ({
    type: b.label,
    count: b.count,
  }));
  return (
    <div className="card">
      <h2 className="mb-3 text-lg font-semibold">Trending theo loại media</h2>
      {data.length === 0 ? (
        <Empty />
      ) : (
        <ResponsiveContainer width="100%" height={260}>
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

function TimelineChart({ stats }: { stats?: RadarStats }) {
  const data = (stats?.timeline ?? []).map((b) => ({
    day: b.label,
    count: b.count,
  }));
  return (
    <div className="card">
      <h2 className="mb-3 text-lg font-semibold">Bài trending theo ngày đăng</h2>
      {data.length === 0 ? (
        <Empty />
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="day" fontSize={12} />
            <YAxis allowDecimals={false} fontSize={12} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="count"
              stroke="#16a34a"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function TrendingTable({ posts }: { posts?: RadarPost[] }) {
  return (
    <section className="card">
      <h2 className="mb-3 text-lg font-semibold">Bảng xếp hạng xu hướng</h2>
      {!posts || posts.length === 0 ? (
        <div className="py-6 text-sm text-gray-400">
          Chưa có bài trending. Thêm tài khoản vào watchlist (mục Tài khoản → theo
          dõi) rồi bấm “Thu thập ngay”.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-gray-500">
              <tr className="border-b">
                <th className="py-2 pr-3">#</th>
                <th className="py-2 pr-3">Nội dung</th>
                <th className="py-2 pr-3">Tác giả</th>
                <th className="py-2 pr-3 text-right">Score</th>
                <th className="py-2 pr-3 text-right">Velocity/h</th>
                <th className="py-2 pr-3 text-right">Like</th>
                <th className="py-2 pr-3 text-right">Reply</th>
                <th className="py-2 pr-3 text-right">Tuổi (h)</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {posts.map((p, i) => (
                <tr key={p.id} className="border-b last:border-0 align-top">
                  <td className="py-2 pr-3 text-gray-400">{i + 1}</td>
                  <td className="py-2 pr-3">
                    <span className="line-clamp-2 max-w-xs text-gray-800">
                      {p.text || (
                        <span className="text-gray-400">(không có text)</span>
                      )}
                    </span>
                    {p.media_type && (
                      <span className="mt-1 inline-block rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
                        {p.media_type}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-gray-600">
                    @{p.author?.username ?? "?"}
                  </td>
                  <td className="py-2 pr-3 text-right font-semibold">
                    {p.score.toFixed(2)}
                  </td>
                  <td
                    className={`py-2 pr-3 text-right ${
                      (p.velocity ?? 0) > 0 ? "text-green-600" : "text-gray-400"
                    }`}
                  >
                    {p.velocity == null ? "—" : p.velocity}
                  </td>
                  <td className="py-2 pr-3 text-right">{p.like_count}</td>
                  <td className="py-2 pr-3 text-right">{p.reply_count}</td>
                  <td className="py-2 pr-3 text-right text-gray-500">
                    {p.age_hours ?? "—"}
                  </td>
                  <td className="py-2">
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
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
