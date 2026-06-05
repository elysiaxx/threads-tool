import { request } from "./client";
import type { Token, UserPublic } from "../types";

export function login(email: string, password: string) {
  // Backend dùng OAuth2PasswordRequestForm: field "username" = email.
  return request<Token>("/auth/login", {
    method: "POST",
    form: true,
    auth: false,
    body: { username: email, password },
  });
}

export function register(email: string, password: string) {
  return request<Token>("/auth/register", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
}

export function me() {
  return request<UserPublic>("/auth/me");
}
