import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createSource, listSources } from "../api/sources";
import { ApiError } from "../api/client";
import type { Source, SourceStatus } from "../types";

const STATUS_STYLE: Record<SourceStatus, string> = {
  pending: "bg-yellow-100 text-yellow-700",
  ready: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export default function SourcesPage() {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: sources, isLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: listSources,
    // Trạng thái cập nhật nền (Celery) -> poll lại mỗi 4s khi còn việc pending.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((s) => s.status === "pending") ? 4000 : false,
  });

  const create = useMutation({
    mutationFn: (u: string) => createSource(u),
    onSuccess: () => {
      setUrl("");
      qc.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Không tạo được source"),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (url.trim()) create.mutate(url.trim());
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold">Media (sources)</h1>
      <p className="text-sm text-gray-500">
        Dán URL ảnh/video công khai. Hệ thống tải về storage và lấy URL public để
        đăng bài (Threads yêu cầu media là URL public).
      </p>

      <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
        <input
          className="input"
          placeholder="https://… (ảnh JPEG/PNG hoặc video MP4/MOV)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button className="btn-primary sm:w-40" disabled={create.isPending}>
          {create.isPending ? "Đang gửi…" : "Thêm media"}
        </button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {isLoading ? (
        <p className="text-sm text-gray-500">Đang tải…</p>
      ) : (sources?.length ?? 0) === 0 ? (
        <p className="text-sm text-gray-500">Chưa có media nào.</p>
      ) : (
        <div className="space-y-3">
          {sources!.map((s) => (
            <SourceRow key={s.id} source={s} />
          ))}
        </div>
      )}
    </div>
  );
}

function SourceRow({ source }: { source: Source }) {
  return (
    <div className="card flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`badge ${STATUS_STYLE[source.status]}`}>
            {source.status}
          </span>
          {source.content_type && (
            <span className="text-xs text-gray-500">{source.content_type}</span>
          )}
        </div>
        <p className="mt-1 truncate text-sm text-gray-700">{source.source_url}</p>
        {source.error && (
          <p className="mt-1 text-xs text-red-600">Lỗi: {source.error}</p>
        )}
      </div>
      {source.media_url && (
        <a
          href={source.media_url}
          target="_blank"
          rel="noreferrer"
          className="btn-secondary shrink-0"
        >
          Xem media
        </a>
      )}
    </div>
  );
}
