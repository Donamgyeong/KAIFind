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
