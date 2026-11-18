import type { Affiliation, Dispute, Role } from "../api/types";

export interface AdminUser {
  userId: string;
  name: string;
  affiliation: Affiliation;
  role: Role;
  collectionRestricted: boolean;
}

export interface AdminDispute extends Dispute {
  finderId: string;
  collectorId: string;
}

export interface Statistics {
  postedCount: number;
  collectedCount: number;
  expiredCount: number;
  asOf: string;
}

export interface AuditLog {
  auditLogId: string;
  actorId: string | null;
  actorType: "MEMBER" | "ADMIN" | "SYSTEM";
  action: string;
  targetType: string;
  targetId: string;
  occurredAt: string;
  metadata: Record<string, unknown>;
}

export const auditActions = [
  "ITEM_STATUS_CHANGED",
  "COLLECTION_MARKED",
  "COLLECTION_UNDONE",
  "DROP_OFF_CHANGED",
  "SENSITIVE_PHOTO_VIEWED",
  "SENSITIVE_DROP_OFF_VIEWED",
  "LOST_REPORT_STATUS_CHANGED",
  "PHOTO_ACCESS_URL_ISSUED",
  "ROLE_CHANGED",
  "REFERENCE_CREATED",
  "REFERENCE_UPDATED",
  "POST_HIDDEN",
  "POST_REPORT_REVIEWED",
  "DISPUTE_REVIEWED",
  "COLLECTION_RESTRICTION_CHANGED",
  "TEXT_ANALYSIS_RETRIED",
  "MATCH_EVALUATION_RETRIED",
];
