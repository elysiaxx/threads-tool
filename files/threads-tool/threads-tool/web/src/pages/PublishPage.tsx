import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listAccounts } from "../api/accounts";
import { listSources } from "../api/sources";
import { createJob, listJobs, retryJob } from "../api/publish";
import { ApiError } from "../api/client";
import type { Job, JobStatus } from "../types";

const STATUS_STYLE: Record<JobStatus, string> = {
  scheduled: "bg-blue-100 text-blue-700",
  pending: "bg-yellow-100 text-yellow-700",
  publishing: "bg-yellow-100 text-yellow-700",
  published: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

const BUSY: JobStatus[] = ["scheduled", "pending", "publishing"];

export default function PublishPage() {
  const qc = useQueryClient();
  const [accountId, setAccountId] = useState("");
  const [text, setText] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [scheduledAt, setScheduledAt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: accounts } = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: listSources });
  const { data: jobs } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: (q) =>
      (q.state.data ?? []).some((j) => BUSY.includes(j.status)) ? 4000 : false,
  });

  const ownedConnected = useMemo(
    () => (accounts ?? []).filter((a) => a.type === "owned" && a.connected),
    [accounts]
  );
  const readySources = useMemo(
    () => (sources ?? []).filter((s) => s.status === "ready"),
    [sources]
  );

  const create = useMutation({
    mutationFn: createJob,
    onSuccess: () => {
      setText("");
      setSelected([]);
      setScheduledAt("");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không tạo được bài đăng"),
  });

  const retry = useMutation({
    mutationFn: (id: string) => retryJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });

  function toggleSource(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!accountId) {
      setError("Chọn tài khoản đăng");
      return;
    }
    create.mutate({
      account_id: accountId,
      text: text.trim() || undefined,
      source_ids: selected,
      // datetime-local (giờ địa phương) -> ISO UTC; rỗng = đăng ngay.
      scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
    });
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <h1 className="text-2xl font-bold">Đăng bài</h1>

      <section className="card">
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Tài khoản</label>
            <select
              className="input"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              <option value="">— Chọn tài khoản owned đã kết nối —</option>
              {ownedConnected.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.username ? `@${a.username}` : a.threads_user_id}
                </option>
              ))}
            </select>
            {ownedConnected.length === 0 && (
              <p className="mt-1 text-xs text-amber-600">
                Chưa có tài khoản owned nào kết nối. Vào mục Tài khoản để kết nối.
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Nội dung</label>
            <textarea
              className="input min-h-[100px]"
              placeholder="Bạn đang nghĩ gì?"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">
              Media ({selected.length} đã chọn{selected.length > 1 ? " · carousel" : ""})
            </label>
            {readySources.length === 0 ? (
              <p className="text-xs text-gray-500">
                Chưa có media “ready”. Thêm ở mục Media trước.
              </p>
            ) : (
              <div className="grid max-h-48 gap-2 overflow-y-auto sm:grid-cols-2">
                {readySources.map((s) => (
                  <label
                    key={s.id}
                    className="flex items-center gap-2 rounded-md border border-gray-200 p-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(s.id)}
                      onChange={() => toggleSource(s.id)}
                    />
                    <span className="truncate">
                      {s.filename || s.source_url}
                      <span className="ml-1 text-xs text-gray-400">
                        {(s.content_type || "").startsWith("video") ? "video" : "ảnh"}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">
              Hẹn giờ (tùy chọn)
            </label>
            <input
              type="datetime-local"
              className="input max-w-xs"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
            <p className="mt-1 text-xs text-gray-400">
              Để trống = đăng ngay. Có giờ = hẹn lịch (worker đăng khi tới hạn).
            </p>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          <button className="btn-primary" disabled={create.isPending}>
            {create.isPending
              ? "Đang gửi…"
              : scheduledAt
                ? "Lên lịch đăng"
                : "Đăng ngay"}
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Lịch sử & hàng đợi</h2>
        {(jobs?.length ?? 0) === 0 ? (
          <p className="text-sm text-gray-500">Chưa có bài đăng nào.</p>
        ) : (
          <div className="space-y-3">
            {jobs!.map((j) => (
              <JobRow key={j.id} job={j} onRetry={() => retry.mutate(j.id)} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function JobRow({ job, onRetry }: { job: Job; onRetry: () => void }) {
  return (
    <div className="card flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`badge ${STATUS_STYLE[job.status]}`}>{job.status}</span>
          <span className="badge bg-gray-100 text-gray-600">{job.media_type}</span>
          {job.scheduled_at && job.status === "scheduled" && (
            <span className="text-xs text-gray-500">
              ⏰ {new Date(job.scheduled_at).toLocaleString()}
            </span>
          )}
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-gray-800">
          {job.text || <span className="text-gray-400">(không có nội dung)</span>}
        </p>
        {job.error && <p className="mt-1 text-xs text-red-600">Lỗi: {job.error}</p>}
        {job.permalink && (
          <a
            href={job.permalink}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-block text-xs text-brand-accent underline"
          >
            Xem bài đã đăng
          </a>
        )}
      </div>
      {job.status === "failed" && (
        <button className="btn-secondary shrink-0" onClick={onRetry}>
          Thử lại
        </button>
      )}
    </div>
  );
}
