/**
 * Core types and interfaces for DocumentAgent and Document Adapters.
 * Vendor-agnostic abstractions ensuring LLMs never interact directly with Univer APIs.
 */

export type DocumentKind = 'document' | 'spreadsheet';

export interface DocumentSection {
  id: string;
  title: string;
  level: number;
  paragraphCount: number;
  previewText: string;
  tables: string[];
  images: string[];
}

export interface TableSummary {
  id: string;
  name?: string;
  rows: number;
  cols: number;
  headerSample: string[];
}

export interface SheetSummary {
  name: string;
  maxRow: number;
  maxCol: number;
  activeRange: string;
}

export interface CanonicalDocumentState {
  documentId: string;
  kind: DocumentKind;
  title: string;
  sections: DocumentSection[];
  tablesSummary: TableSummary[];
  sheetsSummary?: SheetSummary[];
  tagsPresent: string[];
  totalParagraphs: number;
  totalImages: number;
  version: number;
}

export type TargetPosition = 'before' | 'after' | 'inside_end' | 'inside_start' | 'replace_target';

export interface TargetLocator {
  sectionTitle?: string;
  tag?: string;
  anchorText?: string;
  cellRange?: string;
  paragraphIndex?: number;
  position?: TargetPosition;
}

export interface AssetLocator {
  assetId: string;
  url?: string;
  caption?: string;
  width?: number | 'auto';
  height?: number | 'auto';
}

export type DocumentOperationType =
  | 'inspect_document'
  | 'find_section'
  | 'find_text'
  | 'replace_content'
  | 'insert_text'
  | 'insert_image'
  | 'delete_content'
  | 'move_content'
  | 'create_table'
  | 'update_table';

export interface BaseOperation {
  operation: DocumentOperationType;
  documentId?: string;
}

export interface InspectDocumentOperation extends BaseOperation {
  operation: 'inspect_document';
}

export interface FindSectionOperation extends BaseOperation {
  operation: 'find_section';
  sectionTitle: string;
}

export interface FindTextOperation extends BaseOperation {
  operation: 'find_text';
  query: string;
}

export interface InsertImageOperation extends BaseOperation {
  operation: 'insert_image';
  target: TargetLocator;
  asset: AssetLocator;
}

export interface InsertTextOperation extends BaseOperation {
  operation: 'insert_text';
  target: TargetLocator;
  content: string;
}

export interface ReplaceContentOperation extends BaseOperation {
  operation: 'replace_content';
  target: TargetLocator;
  newContent: string;
}

export interface DeleteContentOperation extends BaseOperation {
  operation: 'delete_content';
  target: TargetLocator;
}

export interface MoveContentOperation extends BaseOperation {
  operation: 'move_content';
  sourceTarget: TargetLocator;
  destinationTarget: TargetLocator;
}

export interface CreateTableOperation extends BaseOperation {
  operation: 'create_table';
  target: TargetLocator;
  headers: string[];
  rows?: any[][];
}

export interface UpdateTableOperation extends BaseOperation {
  operation: 'update_table';
  target: TargetLocator;
  action: 'append_row' | 'replace_data' | 'update_cell';
  data: any[][];
}

export type CanonicalDocumentOperation =
  | InspectDocumentOperation
  | FindSectionOperation
  | FindTextOperation
  | InsertImageOperation
  | InsertTextOperation
  | ReplaceContentOperation
  | DeleteContentOperation
  | MoveContentOperation
  | CreateTableOperation
  | UpdateTableOperation;

export interface OperationExecutionResult {
  success: boolean;
  operation: DocumentOperationType;
  elementId?: string;
  message: string;
  error?: string;
  diffSummary?: Record<string, any>;
}

export interface VerificationReport {
  verified: boolean;
  operation: DocumentOperationType;
  targetFound: boolean;
  stateAfter?: CanonicalDocumentState;
  diffDetected: Record<string, any>;
  feedback: string;
}

/**
 * Contract that any document runtime engine (Univer, EigenPal, etc.) must implement.
 */
export interface IDocumentAdapter {
  readonly engineName: string;

  /** Initialize or attach to an existing canvas/engine */
  attach(container: HTMLElement, options?: { kind?: DocumentKind }): Promise<void>;
  detach(): void;

  /** Content loading and export */
  loadTemplate(content: string | Uint8Array, kind: DocumentKind, title?: string): Promise<void>;
  exportContent(format: 'docx' | 'xlsx' | 'json'): Promise<Blob | Uint8Array>;

  /** Canonical Inspection */
  inspect(): Promise<CanonicalDocumentState>;
  findSection(title: string): Promise<DocumentSection | null>;
  findText(query: string): Promise<Array<{ rangeId: string; snippet: string }>>;

  /** Canonical Mutations */
  insertText(op: InsertTextOperation): Promise<OperationExecutionResult>;
  insertImage(op: InsertImageOperation): Promise<OperationExecutionResult>;
  replaceContent(op: ReplaceContentOperation): Promise<OperationExecutionResult>;
  deleteContent(op: DeleteContentOperation): Promise<OperationExecutionResult>;
  createTable(op: CreateTableOperation): Promise<OperationExecutionResult>;
  updateTable(op: UpdateTableOperation): Promise<OperationExecutionResult>;
}
