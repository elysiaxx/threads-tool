import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAuthorizeUrl, listAccounts, trackAccount } from "../api/accounts";
import { pollAccount } from "../api/analytics";
import { ApiError } from "../api/client";
import type { Account } from "../types";

export default function AccountsPage() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const { data: accounts, isLoading } = useQuery({
    queryKey: ["accounts"],
    queryFn: listAccounts,
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
                onPoll={() => poll.mutate(a.id)}
                polling={poll.isPending}
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
          <ul className="flex flex-wrap gap-2">
            {tracked.map((a) => (
              <li
                key={a.id}
                className="rounded-full border border-gray-300 bg-white px-3 py-1 text-sm"
              >
                @{a.username}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function OwnedCard({
  account,
  onPoll,
  polling,
}: {
  account: Account;
  onPoll: () => void;
  polling: boolean;
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
      <button
        className="btn-secondary mt-1 self-start"
        onClick={onPoll}
        disabled={!account.connected || polling}
      >
        Poll insights
      </button>
    </div>
  );
}
