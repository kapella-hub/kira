export interface User {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string;
  created_at: string;
}

export interface LoginRequest {
  username: string;
  password?: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface AuthConfig {
  auth_mode: 'mock' | 'centauth';
  demo_users: string[];
}
