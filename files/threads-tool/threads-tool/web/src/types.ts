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

// --- Trend Radar -------------------------------------------------------------
export interface RadarSettings {
  min_likes: number;
  min_engagement: number;
  max_age_hours: number;
  reply_weight: number;
  quote_weight: number;
  gravity: number;
  min_score: number;
  top_n: number;
}

export interface RadarAuthor {
  id?: string | null;
  username?: string | null;
  full_name?: string | null;
  profile_pic_url?: string | null;
  is_verified?: boolean | null;
}

export interface RadarPost {
  id: string;
  account_id?: string | null;
  source_kind?: string | null;
  source_value?: string | null;
  permalink?: string | null;
  text?: string | null;
  taken_at?: string | null;
  media_type?: string | null;
  image_url?: string | null;
  like_count: number;
  reply_count: number;
  quote_count: number;
  engagement: number;
  score: number;
  velocity?: number | null;
  age_hours?: number | null;
  collected_at?: string | null;
  author: RadarAuthor;
}

export interface RadarBucket {
  label: string;
  count: number;
  engagement: number;
}

export interface RadarStats {
  tracked_posts: number;
  trending_posts: number;
  source_accounts: number;
  avg_engagement: number;
  by_account: RadarBucket[];
  by_media_type: RadarBucket[];
  timeline: RadarBucket[];
  last_collected_at?: string | null;
}

export interface RadarWatchItem {
  account_id: string;
  username?: string | null;
  full_name?: string | null;
  profile_pic_url?: string | null;
  follower_count?: number | null;
  collected_posts: number;
  trending_posts: number;
  last_collected_at?: string | null;
}

export interface RadarStatus {
  state: "idle" | "running";
  started_at?: string | null;
  finished_at?: string | null;
  accounts: number;
  collected: number;
  errors: string[];
}

export interface RadarSession {
  has_cookie: boolean;
  updated_at?: string | null;
  last_check_ok?: boolean | null;
  last_check_at?: string | null;
  last_check_error?: string | null;
  search_doc_id?: string | null;
  search_friendly_name?: string | null;
  doc_id_updated_at?: string | null;
}

export interface RadarSessionTest {
  ok: boolean;
  count?: number;
  error?: string | null;
}

export interface RadarDocIdDiscovery {
  ok: boolean;
  doc_id?: string | null;
  friendly_name?: string | null;
  error?: string | null;
}

export type TargetKind = "keyword" | "hashtag" | "link";

export interface TrackTarget {
  id: string;
  kind: TargetKind;
  value: string;
  collected_posts: number;
  trending_posts: number;
  last_collected_at?: string | null;
  created_at?: string | null;
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
