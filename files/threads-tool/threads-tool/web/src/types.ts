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
  token_expires_at?: string | null;
  connected: boolean;
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
