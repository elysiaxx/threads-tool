// Kiểu dữ liệu khớp với response của backend (FastAPI).

export interface Token {
  access_token: string;
  token_type: string;
}

export interface UserPublic {
  id: string;
  email: string;
  role: string;
  plan: string;
  created_at: string;
}

export type AccountType = "owned" | "tracked";

export interface Account {
  id: string;
  type: AccountType;
  platform: string;
  threads_user_id?: string | null;
  username?: string | null;
  full_name?: string | null;
  follower_count?: number | null;
  media_count?: number | null;
  biography?: string | null;
  profile_pic_url?: string | null;
  last_synced_at?: string | null;
  token_expires_at?: string | null;
  connected: boolean;
  proxy_id?: string | null;
}

export interface ThreadsPublicUser {
  id?: string | null;
  username?: string | null;
  full_name?: string | null;
  profile_pic_url?: string | null;
  is_verified?: boolean | null;
}

export interface ThreadsPublicPost {
  id?: string | null;
  code?: string | null;
  permalink?: string | null;
  text?: string | null;
  taken_at?: string | null;
  media_type?: number | null;
  like_count?: number | null;
  reply_count?: number | null;
  quote_count?: number | null;
  image_url?: string | null;
  video_url?: string | null;
  user: ThreadsPublicUser;
}

export type ProxyProtocol = "http" | "https" | "socks5";

export interface ProxyCheck {
  ok: boolean;
  ip?: string | null;
  error?: string | null;
  checked_at?: string | null;
}

export interface Proxy {
  id: string;
  label: string;
  protocol: ProxyProtocol;
  host: string;
  port: number;
  username?: string | null;
  has_password: boolean;
  active: boolean;
  last_check?: ProxyCheck | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProxyInput {
  label: string;
  protocol: ProxyProtocol;
  host: string;
  port: number;
  username?: string;
  password?: string;
  active: boolean;
}

export type SourceStatus = "pending" | "ready" | "failed";

export interface Source {
  id: string;
  source_url: string;
  status: SourceStatus;
  media_url?: string | null;
  filename?: string | null;
  content_type?: string | null;
  size?: number | null;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TrendTopItem {
  id?: string;
  permalink?: string;
  text?: string;
}

export interface Trend {
  id: string;
  keyword: string;
  ts: string;
  result_count: number;
  top: TrendTopItem[];
}

export type JobStatus =
  | "scheduled"
  | "pending"
  | "publishing"
  | "published"
  | "failed";

export type MediaType = "TEXT" | "IMAGE" | "VIDEO" | "CAROUSEL";

export interface PublishMediaItem {
  source_id?: string | null;
  url: string;
  kind: "image" | "video";
}

export interface Job {
  id: string;
  account_id: string;
  text?: string | null;
  media: PublishMediaItem[];
  media_type: MediaType;
  status: JobStatus;
  scheduled_at?: string | null;
  published_media_id?: string | null;
  permalink?: string | null;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  published_at?: string | null;
}

export interface PublishInput {
  account_id: string;
  text?: string;
  source_ids: string[];
  scheduled_at?: string | null;
}

export interface MetricPoint {
  ts: string;
  views?: number;
  likes?: number;
  replies?: number;
  reposts?: number;
  quotes?: number;
  shares?: number;
  followers_count?: number;
}

export interface Post {
  id: string;
  account_id?: string;
  threads_media_id?: string;
  permalink?: string | null;
  text?: string | null;
  media_type?: string | null;
  published_at?: string | null;
  updated_at?: string | null;
}
