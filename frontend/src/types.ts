export type Role = "user" | "assistant";

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
}

export interface Message {
  id?: number;
  role: Role;
  content: string;
  created_at?: string;
}
