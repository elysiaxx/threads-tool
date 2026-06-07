import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAuthorizeUrl,
  listPublicPosts,
  listAccounts,
  refreshToken,
  syncPublicAccount,
  trackAccount,
} from "../api/accounts";
import { pollAccount } from "../api/analytics";
import { assignProxy, listProxies } from "../api/proxies";
import { ApiError } from "../api/client";
import type { Account, Proxy, ThreadsPublicPost } from "../types";

export default function AccountsPage() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [activeTrackedId, setActiveTrackedId] = useState<string | null>(null);
  const [publicPostKind, setPublicPostKind] = useState<"threads" | "replies">(
    "threads"
  );
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const { data: accounts, isLoading } = useQuery({
    queryKey: ["accounts"],
    queryFn: listAccounts,
  });

  const { data: proxies } = useQuery({ queryKey: ["proxies"], queryFn: listProxies });

  const { data: publicPosts, isFetching: loadingPublicPosts } = useQuery({
    queryKey: ["accounts", activeTrackedId, "public-posts", publicPostKind],
    queryFn: () => listPublicPosts(activeTrackedId!, publicPostKind),
    enabled: Boolean(activeTrackedId),
  });

  const assign = useMutation({
    mutationFn: ({ accountId, proxyId }: { accountId: string; proxyId: string | null }) =>
      assignProxy(accountId, proxyId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không gán được proxy"),
  });

  const track = useMutation({
    mutationFn: (u: string) => trackAccount(u),
    onSuccess: () => {
      setUsername("");
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không thêm được tài khoản"),
  });

  const poll = useMutation({
    mutationFn: (id: string) => pollAccount(id),
    onSuccess: () => setNotice("Đã xếp hàng poll insights cho tài khoản."),
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không poll được"),
  });

  const refresh = useMutation({
    mutationFn: (id: string) => refreshToken(id),
    onSuccess: () => {
      setNotice("Đã gia hạn token.");
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không gia hạn được token"),
  });

  const syncPublic = useMutation({
    mutationFn: (id: string) => syncPublicAccount(id),
    onSuccess: () => {
      setNotice("Đã đồng bộ profile public.");
      qc.invalidateQueries({ queryKey: ["accounts"] });
      if (activeTrackedId) {
        qc.invalidateQueries({
          queryKey: ["accounts", activeTrackedId, "public-posts"],
        });
      }
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không đồng bộ được profile"),
  });

  async function connectThreads() {
    setError(null);
    try {
      const { url } = await getAuthorizeUrl("threads");
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lấy được link OAuth");
    }
  }

  function onTrack(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (username.trim()) track.mutate(username.trim());
  }

  const owned = accounts?.filter((a) => a.type === "owned") ?? [];
  const tracked = accounts?.filter((a) => a.type === "tracked") ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Tài khoản</h1>
        <button className="btn-primary" onClick={connectThreads}>
          Kết nối Threads (OAuth)
        </button>
      </div>

      {notice && (
        <div className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700">
          {notice}
        </div>
      )}
      {error && (
        <div className="rounded-md bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold">Tài khoản của tôi (owned)</h2>
        {isLoading ? (
          <p className="text-sm text-gray-500">Đang tải…</p>
        ) : owned.length === 0 ? (
          <p className="text-sm text-gray-500">
            Chưa có tài khoản nào. Bấm “Kết nối Threads” để bắt đầu.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {owned.map((a) => (
              <OwnedCard
                key={a.id}
                account={a}
                proxies={proxies ?? []}
                onPoll={() => poll.mutate(a.id)}
                polling={poll.isPending}
                onRefresh={() => refresh.mutate(a.id)}
                refreshing={refresh.isPending}
                onAssignProxy={(proxyId) =>
                  assign.mutate({ accountId: a.id, proxyId })
                }
              />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Theo dõi đối thủ (tracked)</h2>
        <form onSubmit={onTrack} className="mb-4 flex gap-2">
          <input
            className="input max-w-xs"
            placeholder="username Threads"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <button className="btn-secondary" disabled={track.isPending}>
            {track.isPending ? "Đang thêm…" : "Thêm"}
          </button>
        </form>
        {tracked.length === 0 ? (
          <p className="text-sm text-gray-500">Chưa theo dõi tài khoản nào.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {tracked.map((a) => (
              <TrackedCard
                key={a.id}
                account={a}
                active={activeTrackedId === a.id}
                syncing={syncPublic.isPending}
                onSync={() => syncPublic.mutate(a.id)}
                onShow={(kind) => {
                  setPublicPostKind(kind);
                  setActiveTrackedId(a.id);
                }}
              />
            ))}
          </div>
        )}
      </section>

      {activeTrackedId && (
        <PublicPostsPanel
          kind={publicPostKind}
          posts={publicPosts ?? []}
          loading={loadingPublicPosts}
          onKindChange={setPublicPostKind}
        />
      )}
    </div>
  );
}

function OwnedCard({
  account,
  proxies,
  onPoll,
  polling,
  onRefresh,
  refreshing,
  onAssignProxy,
}: {
  account: Account;
  proxies: Proxy[];
  onPoll: () => void;
  polling: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  onAssignProxy: (proxyId: string | null) => void;
}) {
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="font-medium">
          {account.username ? `@${account.username}` : account.threads_user_id || "—"}
        </span>
        <span
          className={`badge ${
            account.connected
              ? "bg-green-100 text-green-700"
              : "bg-yellow-100 text-yellow-700"
          }`}
        >
          {account.connected ? "Đã kết nối" : "Chưa có token"}
        </span>
      </div>
      {account.token_expires_at && (
        <p className="text-xs text-gray-500">
          Token hết hạn: {new Date(account.token_expires_at).toLocaleDateString()}
        </p>
      )}

      <label className="mt-1 block text-xs text-gray-500">
        Proxy
        <select
          className="input mt-1 text-sm"
          value={account.proxy_id ?? ""}
          onChange={(e) => onAssignProxy(e.target.value || null)}
        >
          <option value="">— Pool xoay vòng —</option>
          {proxies.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label} ({p.protocol})
            </option>
          ))}
        </select>
      </label>

      <div className="mt-1 flex gap-2">
        <button
          className="btn-secondary"
          onClick={onPoll}
          disabled={!account.connected || polling}
        >
          Poll insights
        </button>
        <button
          className="btn-secondary"
          onClick={onRefresh}
          disabled={!account.connected || refreshing}
        >
          {refreshing ? "Đang gia hạn…" : "Gia hạn token"}
        </button>
      </div>
    </div>
  );
}

function formatCount(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("vi-VN", { notation: "compact" }).format(value);
}

function TrackedCard({
  account,
  active,
  syncing,
  onSync,
  onShow,
}: {
  account: Account;
  active: boolean;
  syncing: boolean;
  onSync: () => void;
  onShow: (kind: "threads" | "replies") => void;
}) {
  return (
    <div className={`card flex flex-col gap-3 ${active ? "ring-1 ring-black" : ""}`}>
      <div className="flex items-start gap-3">
        {account.profile_pic_url ? (
          <img
            src={account.profile_pic_url}
            alt=""
            className="h-11 w-11 rounded-full object-cover"
          />
        ) : (
          <div className="h-11 w-11 rounded-full bg-gray-200" />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">
            {account.full_name || `@${account.username}`}
          </div>
          <div className="truncate text-sm text-gray-500">@{account.username}</div>
        </div>
      </div>

      {account.biography && (
        <p className="line-clamp-2 text-sm text-gray-700">{account.biography}</p>
      )}

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <div className="text-xs text-gray-500">Followers</div>
          <div className="font-medium">{formatCount(account.follower_count)}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Threads</div>
          <div className="font-medium">{formatCount(account.media_count)}</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button className="btn-secondary" onClick={() => onShow("threads")}>
          Xem bài
        </button>
        <button className="btn-secondary" onClick={() => onShow("replies")}>
          Xem replies
        </button>
        <button className="btn-secondary" disabled={syncing} onClick={onSync}>
          {syncing ? "Đang đồng bộ…" : "Đồng bộ"}
        </button>
      </div>
    </div>
  );
}

function PublicPostsPanel({
  kind,
  posts,
  loading,
  onKindChange,
}: {
  kind: "threads" | "replies";
  posts: ThreadsPublicPost[];
  loading: boolean;
  onKindChange: (kind: "threads" | "replies") => void;
}) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Bài viết public</h2>
        <div className="inline-flex rounded-md border border-gray-300 bg-white p-1">
          {(["threads", "replies"] as const).map((item) => (
            <button
              key={item}
              className={`rounded px-3 py-1 text-sm ${
                kind === item ? "bg-black text-white" : "text-gray-700"
              }`}
              onClick={() => onKindChange(item)}
            >
              {item === "threads" ? "Bài viết" : "Replies"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">Đang tải bài viết…</p>
      ) : posts.length === 0 ? (
        <p className="text-sm text-gray-500">Chưa có dữ liệu public.</p>
      ) : (
        <div className="grid gap-3">
          {posts.map((post, index) => (
            <article key={post.id || post.code || index} className="card">
              <div className="mb-2 flex items-center justify-between gap-3 text-sm text-gray-500">
                <span>@{post.user.username}</span>
                {post.permalink && (
                  <a
                    href={post.permalink}
                    target="_blank"
                    rel="noreferrer"
                    className="text-gray-900 underline"
                  >
                    Mở Threads
                  </a>
                )}
              </div>
              {post.text && <p className="whitespace-pre-wrap text-sm">{post.text}</p>}
              {post.image_url && (
                <img
                  src={post.image_url}
                  alt=""
                  className="mt-3 max-h-72 rounded-md object-cover"
                />
              )}
              <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
                <span>{formatCount(post.like_count)} likes</span>
                <span>{formatCount(post.reply_count)} replies</span>
                {post.taken_at && (
                  <span>{new Date(post.taken_at).toLocaleString()}</span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
