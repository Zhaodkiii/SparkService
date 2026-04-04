export interface ApiEnvelope<T> {
  code: number;
  msg: string;
  data: T;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface MenuNode {
  code: string;
  name: string;
  path: string;
  children?: MenuNode[];
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  date_joined: string;
  last_login: string | null;
}
