import { useEffect, useRef, useState } from "react";
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
  addTarget,
  collectRadar,
  deleteSession,
  discoverSessionDocId,
  getRadarSettings,
  getRadarStats,
  getRadarStatus,
  getSession,
  getWatchlist,
  listRadarPosts,
  listTargets,
  removeTarget,
  saveSession,
  testSession,
  updateRadarSettings,
} from "../api/radar";
import { ApiError, getToken } from "../api/client";
import type {
  RadarPost,
  RadarSettings,
  RadarStats,
  RadarStatus,
  RadarWatchItem,
  TargetKind,
} from "../types";

type CookieExportItem = {
  name?: unknown;
  value?: unknown;
};

const COOKIE_PRIORITY = ["sessionid", "csrftoken", "ds_user_id"];

function cookieHeaderFromExport(items: CookieExportItem[]) {
  const values = new Map<string, string>();
  const order: string[] = [];
  for (const item of items) {
    const name = typeof item.name === "string" ? item.name.trim() : "";
    const value = typeof item.value === "string" ? item.value.trim() : "";
    if (!name || !value) continue;
    if (!values.has(name)) order.push(name);
    values.set(name, value);
  }

  const names = COOKIE_PRIORITY.filter((name) => values.has(name));
  for (const name of order) {
    if (!names.includes(name)) names.push(name);
  }
  return {
    cookie: names.map((name) => `${name}=${values.get(name)}`).join("; "),
    hasSessionId: values.has("sessionid"),
  };
}

function normalizeCookieFileText(text: string) {
  const raw = text.trim();
  if (!raw) return { cookie: "", warning: "File cookie đang rỗng." };

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return { cookie: raw, warning: "File không phải JSON cookie array; đã đưa text gốc vào ô cookie." };
    }
    const result = cookieHeaderFromExport(parsed as CookieExportItem[]);
    if (!result.cookie) {
      return { cookie: "", warning: "File cookie không có name/value hợp lệ." };
    }
    return {
      cookie: result.cookie,
      warning: result.hasSessionId ? null : "File cookie thiếu sessionid.",
    };
  } catch {
    return { cookie: raw, warning: "File không phải JSON hợp lệ; đã đưa text gốc vào ô cookie." };
  }
}

export default function TrendRadarPage() {
  const qc = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: status } = useQuery({
    queryKey: ["radar-status"],
    queryFn: getRadarStatus,
    refetchInterval: (q) =>
      (q.state.data as RadarStatus | undefined)?.state === "running" ? 2500 : false,
  });
  const collecting = status?.state === "running";
  const liveInterval = collecting ? 4000 : (false as const);

  const { data: settings } = useQuery({
    queryKey: ["radar-settings"],
    queryFn: getRadarSettings,
  });
  const { data: stats } = useQuery({
    queryKey: ["radar-stats"],
    queryFn: getRadarStats,
    refetchInterval: liveInterval,
  });
  const { data: posts } = useQuery({
    queryKey: ["radar-posts"],
    queryFn: () => listRadarPosts(),
    refetchInterval: liveInterval,
  });
  const { data: watchlist } = useQuery({
    queryKey: ["radar-watchlist"],
    queryFn: getWatchlist,
    refetchInterval: liveInterval,
  });

  // Khi thu thập vừa xong (running -> idle), làm mới lần cuối để lấy số liệu chốt.
  const wasCollecting = useRef(false);
  useEffect(() => {
    if (wasCollecting.current && !collecting) refresh();
    wasCollecting.current = collecting;
  }, [collecting]);

  const collect = useMutation({
    mutationFn: collectRadar,
    onSuccess: () => {
      setError(null);
      setNotice("Đã bắt đầu thu thập watchlist — số liệu sẽ tự cập nhật khi xong.");
      qc.invalidateQueries({ queryKey: ["radar-status"] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không thu thập được"),
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ["radar-stats"] });
    qc.invalidateQueries({ queryKey: ["radar-posts"] });
    qc.invalidateQueries({ queryKey: ["radar-watchlist"] });
    qc.invalidateQueries({ queryKey: ["radar-targets"] });
    qc.invalidateQueries({ queryKey: ["radar-status"] });
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
            disabled={collect.isPending || collecting}
          >
            {collecting
              ? "Đang thu thập…"
              : collect.isPending
              ? "Đang gửi…"
              : "Thu thập ngay"}
          </button>
        </div>
      </div>

      {notice && <p className="text-sm text-green-700">{notice}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <CollectionStatus status={status} />

      <StatCards stats={stats} />

      <Watchlist items={watchlist} collecting={collecting} />

      <SessionPanel onError={setError} onNotice={setNotice} />

      <TargetsPanel collecting={collecting} onError={setError} />

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

function CollectionStatus({ status }: { status?: RadarStatus }) {
  if (!status) return null;
  const running = status.state === "running";
  return (
    <section
      className={`card border-l-4 ${
        running ? "border-l-blue-500" : "border-l-gray-200"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {running ? (
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-blue-500" />
          ) : (
            <span className="h-2.5 w-2.5 rounded-full bg-gray-300" />
          )}
          <span className="font-medium">
            {running ? "Đang thu thập watchlist…" : "Sẵn sàng"}
          </span>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-gray-600">
          <span>
            Tài khoản: <b>{status.accounts}</b>
          </span>
          <span>
            Bài thu thập: <b>{status.collected}</b>
          </span>
          {status.finished_at && !running && (
            <span className="text-gray-400">
              Xong: {new Date(status.finished_at).toLocaleString()}
            </span>
          )}
          {running && status.started_at && (
            <span className="text-gray-400">
              Bắt đầu: {new Date(status.started_at).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>
      {status.errors.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-amber-700">
          {status.errors.slice(0, 5).map((e, i) => (
            <li key={i}>⚠ {e}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SessionPanel({
  onError,
  onNotice,
}: {
  onError: (m: string) => void;
  onNotice: (m: string) => void;
}) {
  const qc = useQueryClient();
  const [cookie, setCookie] = useState("");
  const [cookieFileWarning, setCookieFileWarning] = useState<string | null>(null);

  const { data: session } = useQuery({
    queryKey: ["radar-session"],
    queryFn: getSession,
  });

  const save = useMutation({
    mutationFn: () => saveSession(cookie.trim()),
    onSuccess: () => {
      setCookie("");
      setCookieFileWarning(null);
      onNotice("Đã lưu cookie phiên (mã hoá). Bấm 'Kiểm tra' để xác thực.");
      qc.invalidateQueries({ queryKey: ["radar-session"] });
    },
    onError: (e) =>
      onError(e instanceof ApiError ? e.message : "Không lưu được cookie"),
  });
  const test = useMutation({
    mutationFn: testSession,
    onSuccess: (r) => {
      if (r.ok) onNotice(`Cookie hợp lệ ✓ (tìm thử được ${r.count ?? 0} bài).`);
      else onError(`Cookie không dùng được: ${r.error ?? "lỗi"}`);
      qc.invalidateQueries({ queryKey: ["radar-session"] });
    },
  });
  const del = useMutation({
    mutationFn: deleteSession,
    onSuccess: () => {
      onNotice("Đã xoá cookie phiên.");
      qc.invalidateQueries({ queryKey: ["radar-session"] });
    },
  });

  const discover = useMutation({
    mutationFn: discoverSessionDocId,
    onSuccess: (r) => {
      if (r.ok) {
        onNotice(`Đã dò doc_id ${r.doc_id} (${r.friendly_name ?? "search query"}).`);
      } else {
        onError(`Không dò được doc_id: ${r.error ?? "lỗi"}`);
      }
      qc.invalidateQueries({ queryKey: ["radar-session"] });
    },
    onError: (e) =>
      onError(e instanceof ApiError ? e.message : "Không dò được doc_id"),
  });

  const has = session?.has_cookie;

  function handleCookieFile(file: File | undefined) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      const result = normalizeCookieFileText(text);
      setCookie(result.cookie);
      setCookieFileWarning(result.warning);
    };
    reader.onerror = () => {
      setCookieFileWarning("Không đọc được file cookie.");
    };
    reader.readAsText(file);
  }

  async function copyHelperToken() {
    const token = getToken();
    if (!token) {
      onError("Không tìm thấy token đăng nhập app.");
      return;
    }
    await navigator.clipboard.writeText(token);
    onNotice("Đã copy app token cho browser helper.");
  }

  return (
    <section className="card border-l-4 border-l-amber-400">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Phiên Threads (cookie để search)</h2>
        {session && (
          <span
            className={`rounded-full px-2 py-0.5 text-xs ${
              has
                ? session.last_check_ok
                  ? "bg-green-100 text-green-700"
                  : "bg-amber-100 text-amber-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {has
              ? session.last_check_ok
                ? "Đã kết nối ✓"
                : "Đã lưu cookie (chưa kiểm tra)"
              : "Chưa có cookie"}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-gray-500">
        Search theo từ khoá/hashtag/link cần phiên đăng nhập. Mở{" "}
        <b>threads.com</b> (đã đăng nhập) → DevTools (F12) → Application → Cookies →
        copy giá trị <b>sessionid</b> (hoặc cả chuỗi cookie) rồi dán vào đây. Cookie
        được lưu <b>mã hoá</b> và không hiển thị lại. Nên dùng <b>account phụ</b>.
      </p>
      <p className="mt-1 text-xs text-gray-500">
        Cách ổn định hơn: load extension trong <b>browser-helper</b>, copy helper token,
        mở Threads qua extension rồi gửi cookie + doc_id về app.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          className="input max-w-md flex-1"
          type="password"
          placeholder="sessionid=...; ds_user_id=...; csrftoken=..."
          value={cookie}
          onChange={(e) => {
            setCookie(e.target.value);
            setCookieFileWarning(null);
          }}
        />
        <label className="btn-secondary cursor-pointer">
          Upload file
          <input
            type="file"
            accept=".txt,.json,application/json,text/plain"
            className="hidden"
            onChange={(e) => {
              handleCookieFile(e.target.files?.[0]);
              e.currentTarget.value = "";
            }}
          />
        </label>
        <button
          className="btn-primary"
          onClick={() => cookie.trim() && save.mutate()}
          disabled={save.isPending || !cookie.trim()}
        >
          {save.isPending ? "Đang lưu…" : "Lưu cookie"}
        </button>
        <button
          className="btn-secondary"
          onClick={() => test.mutate()}
          disabled={test.isPending || !has}
        >
          {test.isPending ? "Đang kiểm tra…" : "Kiểm tra"}
        </button>
        <button
          className="btn-secondary"
          onClick={() => discover.mutate()}
          disabled={discover.isPending || !has}
        >
          {discover.isPending ? "Đang dò..." : "Dò doc_id"}
        </button>
        <button className="btn-secondary" onClick={copyHelperToken}>
          Copy helper token
        </button>
        {has && (
          <button
            className="btn-secondary text-red-600"
            onClick={() => del.mutate()}
            disabled={del.isPending}
          >
            Xoá
          </button>
        )}
      </div>
      {session?.last_check_error && !session.last_check_ok && (
        <p className="mt-2 text-xs text-amber-700">⚠ {session.last_check_error}</p>
      )}
      {cookieFileWarning && (
        <p className="mt-2 text-xs text-amber-700">{cookieFileWarning}</p>
      )}
      {session?.search_doc_id && (
        <p className="mt-2 text-xs text-gray-500">
          doc_id search: <b>{session.search_doc_id}</b>
          {session.search_friendly_name ? ` (${session.search_friendly_name})` : ""}
          {session.has_search_variables_template ? " - có variables template" : ""}
          {session.doc_id_updated_at
            ? ` - ${new Date(session.doc_id_updated_at).toLocaleString()}`
            : ""}
        </p>
      )}
    </section>
  );
}

const KIND_LABEL: Record<TargetKind, string> = {
  keyword: "Từ khoá",
  hashtag: "Hashtag",
  link: "Link/URL",
};
const KIND_PLACEHOLDER: Record<TargetKind, string> = {
  keyword: "vd: trí tuệ nhân tạo",
  hashtag: "vd: threadsvn (tự thêm #)",
  link: "vd: example.com hoặc link 1 bài Threads",
};

function TargetsPanel({
  collecting,
  onError,
}: {
  collecting: boolean;
  onError: (m: string) => void;
}) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<TargetKind>("keyword");
  const [value, setValue] = useState("");

  const { data: targets } = useQuery({
    queryKey: ["radar-targets"],
    queryFn: listTargets,
    refetchInterval: collecting ? 4000 : (false as const),
  });

  const add = useMutation({
    mutationFn: () => addTarget(kind, value.trim()),
    onSuccess: () => {
      setValue("");
      qc.invalidateQueries({ queryKey: ["radar-targets"] });
    },
    onError: (e) =>
      onError(e instanceof ApiError ? e.message : "Không thêm được nguồn"),
  });
  const del = useMutation({
    mutationFn: (id: string) => removeTarget(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["radar-targets"] }),
  });

  return (
    <section className="card">
      <h2 className="mb-1 text-lg font-semibold">
        Nguồn theo dõi: từ khoá / hashtag / link
      </h2>
      <p className="mb-3 text-xs text-gray-500">
        Ngoài watchlist tài khoản, bạn có thể bám trend theo từ khoá, hashtag hoặc
        link. Mỗi lần thu thập sẽ tìm bài public khớp và chấm điểm như trên.
      </p>
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) add.mutate();
        }}
      >
        <select
          className="input max-w-[140px]"
          value={kind}
          onChange={(e) => setKind(e.target.value as TargetKind)}
        >
          {(Object.keys(KIND_LABEL) as TargetKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
        <input
          className="input max-w-sm flex-1"
          placeholder={KIND_PLACEHOLDER[kind]}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button className="btn-primary" disabled={add.isPending}>
          {add.isPending ? "Đang thêm…" : "Thêm nguồn"}
        </button>
      </form>

      {targets && targets.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-gray-500">
              <tr className="border-b">
                <th className="py-2 pr-3">Loại</th>
                <th className="py-2 pr-3">Giá trị</th>
                <th className="py-2 pr-3 text-right">Đã thu thập</th>
                <th className="py-2 pr-3 text-right">Trending</th>
                <th className="py-2 pr-3">Gần nhất</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {targets.map((t) => (
                <tr key={t.id} className="border-b last:border-0">
                  <td className="py-2 pr-3">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                      {KIND_LABEL[t.kind]}
                    </span>
                  </td>
                  <td className="py-2 pr-3 font-medium">{t.value}</td>
                  <td className="py-2 pr-3 text-right">
                    {t.collected_posts || (
                      <span className="text-gray-300">{collecting ? "…" : "0"}</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right font-semibold">
                    {t.trending_posts}
                  </td>
                  <td className="py-2 pr-3 text-gray-500">
                    {t.last_collected_at
                      ? new Date(t.last_collected_at).toLocaleString()
                      : "Chưa thu thập"}
                  </td>
                  <td className="py-2 text-right">
                    <button
                      className="text-xs text-red-600 hover:underline"
                      onClick={() => del.mutate(t.id)}
                      disabled={del.isPending}
                    >
                      Xoá
                    </button>
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

function Watchlist({
  items,
  collecting,
}: {
  items?: RadarWatchItem[];
  collecting: boolean;
}) {
  return (
    <section className="card">
      <h2 className="mb-3 text-lg font-semibold">
        Watchlist {items ? `(${items.length})` : ""}
      </h2>
      {!items || items.length === 0 ? (
        <div className="py-4 text-sm text-gray-400">
          Chưa theo dõi tài khoản nào. Vào <b>Tài khoản</b> → thêm username Threads
          công khai để đưa vào watchlist, rồi bấm “Thu thập ngay”.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-gray-500">
              <tr className="border-b">
                <th className="py-2 pr-3">Tài khoản</th>
                <th className="py-2 pr-3 text-right">Follower</th>
                <th className="py-2 pr-3 text-right">Đã thu thập</th>
                <th className="py-2 pr-3 text-right">Trending</th>
                <th className="py-2 pr-3">Lần thu thập gần nhất</th>
              </tr>
            </thead>
            <tbody>
              {items.map((w) => (
                <tr key={w.account_id} className="border-b last:border-0">
                  <td className="py-2 pr-3">
                    <div className="flex items-center gap-2">
                      {w.profile_pic_url ? (
                        <img
                          src={w.profile_pic_url}
                          alt=""
                          className="h-7 w-7 rounded-full object-cover"
                          referrerPolicy="no-referrer"
                        />
                      ) : (
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gray-100 text-xs text-gray-400">
                          @
                        </span>
                      )}
                      <div className="leading-tight">
                        <div className="font-medium">@{w.username ?? "?"}</div>
                        {w.full_name && (
                          <div className="text-xs text-gray-400">{w.full_name}</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="py-2 pr-3 text-right text-gray-600">
                    {w.follower_count ?? "—"}
                  </td>
                  <td className="py-2 pr-3 text-right">
                    {w.collected_posts || (
                      <span className="text-gray-300">
                        {collecting ? "…" : "0"}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right font-semibold">
                    {w.trending_posts}
                  </td>
                  <td className="py-2 pr-3 text-gray-500">
                    {w.last_collected_at
                      ? new Date(w.last_collected_at).toLocaleString()
                      : "Chưa thu thập"}
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
                <th className="py-2 pr-3">Nguồn</th>
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
                  <td className="py-2 pr-3 text-xs text-gray-500">
                    {p.source_kind ? (
                      <>
                        <span className="rounded bg-gray-100 px-1.5 py-0.5">
                          {p.source_kind}
                        </span>
                        {p.source_value && (
                          <div className="mt-1 max-w-[160px] truncate">
                            {p.source_value}
                          </div>
                        )}
                      </>
                    ) : (
                      "-"
                    )}
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
