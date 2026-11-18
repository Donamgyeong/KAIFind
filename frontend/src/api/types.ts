export type Language = "ko" | "en";
export type Role = "MEMBER" | "ADMIN";
export type Affiliation = "STUDENT" | "FACULTY" | "STAFF";
export type ItemStatus = "POSTED" | "COLLECTED" | "EXPIRED";
export type ProcessingStatus = "PENDING" | "PROCESSING" | "READY" | "FAILED";

export interface User {
  userId: string;
  name: string;
  email: string;
  affiliation: Affiliation;
  role: Role;
  language: Language;
}

export interface MockAccount {
  mockAccountId: string;
  displayName: string;
  affiliation: Affiliation;
  role: Role;
}

export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

export interface Building {
  buildingId: string;
  code: string;
  nameKo: string;
  nameEn: string;
  active: boolean;
  postedCount?: number | null;
}

export interface Category {
  categoryId: string;
  nameKo: string;
  nameEn: string;
  active: boolean;
  sensitive: boolean;
}

export interface Photo {
  photoId: string;
  altText: string;
  accessRequiresLogin: boolean;
}

export interface ItemSummary {
  itemId: string;
  category: Category;
  title: string;
  status: ItemStatus;
  foundBuilding: Building;
  foundAt: string;
  createdAt: string;
  photos: Photo[];
  sensitive: boolean;
  hidden: boolean;
}

export interface ItemDetail extends ItemSummary {
  description: string;
  foundLocationDescription: string;
  finder: { userId: string };
  updatedAt: string;
  postedAt: string;
  expiresAt: string;
  closedAt: string | null;
  analysisStatus: ProcessingStatus;
}

export interface PhotoAttachment {
  photoId: string;
  altText: string;
}

export type DropOffInput =
  | { mode: "KEPT_BY_FINDER" }
  | {
      mode: "DROP_OFF";
      buildingId: string;
      spotDescription: string;
      photo?: PhotoAttachment;
    };

export interface DropOff {
  mode: DropOffInput["mode"];
  building: Building | null;
  spotDescription: string | null;
  photo: Photo | null;
  updatedAt: string;
}

export interface DropOffHistory {
  historyId: string;
  changedByUserId: string;
  changedAt: string;
  before: DropOff | null;
  after: DropOff;
}

export type LostReportStatus = "OPEN" | "RESOLVED" | "CLOSED";

export interface LostReportInput {
  categoryId: string;
  description: string;
  possibleBuildingIds: string[];
  lostDateFrom: string;
  lostDateTo: string;
  privateIdentifyingDetails: string;
}

export interface LostReport extends Omit<
  LostReportInput,
  "privateIdentifyingDetails"
> {
  reportId: string;
  ownerId: string;
  status: LostReportStatus;
  createdAt: string;
  updatedAt: string;
  expiresAt: string;
  closedAt: string | null;
  analysisStatus: ProcessingStatus;
  matchingStatus: ProcessingStatus;
  privateIdentifyingDetails?: string | null;
}

export interface MatchCandidate {
  candidateId: string;
  reportId: string;
  itemId: string;
  matchedAt: string;
  matchedBy: ("BUILDING" | "KEYWORD")[];
  item: {
    itemId: string;
    categoryId: string;
    foundBuildingId: string;
    title: string;
    foundAt: string;
    status: ItemStatus;
    sensitive: boolean;
  };
}

export interface MatchPage extends Page<MatchCandidate> {
  analysisStatus: ProcessingStatus;
  matchingStatus: ProcessingStatus;
  isComplete: boolean;
}

export interface Collection {
  collectionId: string;
  itemId: string;
  collectorId: string;
  collectedAt: string;
  status: "COLLECTED";
}

export interface Dispute {
  disputeId: string;
  itemId: string;
  collectionId: string;
  reason: string;
  status: "OPEN" | "RESOLVED";
  decision: "UPHELD" | "DISMISSED" | null;
  createdAt: string;
  resolvedAt: string | null;
}

export interface Conversation {
  conversationId: string;
  itemId: string;
  finderId: string;
  memberId: string;
  createdAt: string;
  updatedAt: string;
}

export interface Message {
  messageId: string;
  conversationId: string;
  senderId: string;
  content: string;
  createdAt: string;
}

export interface NotificationSettings {
  emailEnabled: boolean;
  matchEmail: boolean;
  collectionEmail: boolean;
  expiryEmail: boolean;
  keywordEmail: boolean;
}

export interface Notification {
  notificationId: string;
  type: "MATCH_CANDIDATE" | "ITEM_COLLECTED" | "ITEM_EXPIRED" | "KEYWORD_MATCH";
  message: string;
  targetPath: string;
  itemId: string | null;
  reportId: string | null;
  createdAt: string;
  readAt: string | null;
}

export interface Subscription {
  subscriptionId: string;
  keyword: string;
  createdAt: string;
}

export type ReportReason = "INAPPROPRIATE" | "SPAM" | "OTHER";

export interface PostReport {
  reportId: string;
  itemId: string;
  reporterId: string;
  reasonCode: ReportReason;
  details: string;
  status: "OPEN" | "REVIEWED";
  decision: "HIDE" | "DISMISS" | null;
  createdAt: string;
  reviewedAt: string | null;
  reviewerId: string | null;
}
