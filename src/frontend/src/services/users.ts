import api from "./api";
import type { User } from "@/types/api";

export interface ProvisionUserRequest {
  username: string;
  email: string;
  role: "admin" | "perito";
}

export interface UpdateUserRequest {
  email?: string;
  role?: "admin" | "perito";
  is_active?: boolean;
}

export async function listUsers(): Promise<User[]> {
  const response = await api.get<User[]>("/users");
  return response.data;
}

export async function provisionUser(data: ProvisionUserRequest): Promise<User> {
  const response = await api.post<User>("/users", data);
  return response.data;
}

export async function updateUser(userId: string, data: UpdateUserRequest): Promise<User> {
  const response = await api.put<User>(`/users/${userId}`, data);
  return response.data;
}

export async function resetUserPassword(userId: string): Promise<User> {
  const response = await api.post<User>(`/users/${userId}/reset-password`);
  return response.data;
}
