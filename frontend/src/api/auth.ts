import { get, post } from './client.ts';
import type { AuthConfig, AuthResponse, User } from '@/types/user.ts';

export function getAuthConfig(): Promise<AuthConfig> {
  return get<AuthConfig>('/auth/config');
}

export function login(username: string, password?: string): Promise<AuthResponse> {
  return post<AuthResponse>('/auth/login', { username, password: password || '' });
}

export function fetchMe(): Promise<User> {
  return get<User>('/auth/me');
}
