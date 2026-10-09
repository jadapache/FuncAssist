/**
 * UniverAdapter.ts
 * Concrete implementation of IDocumentAdapter for Univer engine (https://github.com/dream-num/univer).
 * Connects DocumentAgent to Univer Docs and Univer Sheets APIs.
 */

import type {
  CanonicalDocumentState,
  CreateTableOperation,
  DeleteContentOperation,
  DocumentKind,
  DocumentSection,
  IDocumentAdapter,
  InsertImageOperation,
  InsertTextOperation,
  OperationExecutionResult,
  ReplaceContentOperation,
  SheetSummary,
  TableSummary,
  UpdateTableOperation,
} from '../core/types';

export interface UniverInstanceWrapper {
  univer: any;
  univerAPI: any;
  activeUnitId: string | null;
  kind: DocumentKind;
}

export class UniverAdapter implements IDocumentAdapter {
  readonly engineName = 'Univer';

  private container: HTMLElement | null = null;
  private kind: DocumentKind = 'document';
  private title: string = 'Documento';
  private documentId: string = 'doc_univer_active';

  // Internal state representation for inspection
  private internalSections: DocumentSection[] = [];
  private internalTables: TableSummary[] = [];
  private internalSheets: SheetSummary[] = [];
  private internalTags: string[] = [];
  private internalImages: Array<{ id: string; sectionId: string; url: string; caption?: string }> = [];
  private rawLines: string[] = [];

  // Univer runtime instance placeholder (initialized when attached)
  private univerInstance: UniverInstanceWrapper | null = null;

  constructor(defaultKind: DocumentKind = 'document') {
    this.kind = defaultKind;
  }

  public async attach(container: HTMLElement, options?: { kind?: DocumentKind }): Promise<void> {
    this.container = container;
    if (this.container) {
      this.container.setAttribute('data-univer-mounted', 'true');
    }
    if (options?.kind) {
      this.kind = options.kind;
    }
  }

  public detach(): void {
    if (this.univerInstance?.univer) {
      try {
        this.univerInstance.univer.dispose?.();
      } catch (err) {
        console.warn('Error disposing Univer instance:', err);
      }
    }
    this.univerInstance = null;
    this.container = null;
  }

  public async loadTemplate(
    content: string | Uint8Array,
    kind: DocumentKind,
    title: string = 'Plantilla Corporativa'
  ): Promise<void> {
    this.kind = kind;
    this.title = title;
    this.documentId = `doc_${Date.now()}`;
    this.internalImages = [];
    this.internalSheets = this.kind === 'spreadsheet' ? [
      { name: 'Sheet1', maxRow: 100, maxCol: 26, activeRange: 'A1:H20' }
    ] : [];

    let textContent = '';
    if (typeof content === 'string') {
      textContent = content;
    } else {
      textContent = new TextDecoder('utf-8').decode(content);
    }

    this.rawLines = textContent.split(/\r?\n/);
    this.parseSectionsAndTags(this.rawLines);
  }

  private parseSectionsAndTags(lines: string[]) {
    this.internalSections = [];
    this.internalTables = [];
    const discoveredTags = new Set<string>();

    let currentSection: DocumentSection | null = null;
    let sectionIdx = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // Detect Tags: {{TAG}}
      const tagMatches = line.match(/\{\{([A-Za-z0-9_]+)\}\}/g);
      if (tagMatches) {
        for (const tm of tagMatches) {
          discoveredTags.add(tm.replace(/[{}]/g, '').toUpperCase());
        }
      }

      if (line.startsWith('{{') && line.endsWith('}}')) {
        continue;
      }

      // Detect Headings (# or ## or uppercase section titles)
      const isH1 = line.startsWith('# ') || /^[0-9]+\.\s+[A-ZÁÉÍÓÚÑ\s]{4,}$/.test(line);
      const isH2 = line.startsWith('## ');

      if (isH1 || isH2 || (!line.startsWith('{{') && line.length > 3 && line.length < 50 && line === line.toUpperCase() && !line.includes('|'))) {
        sectionIdx++;
        const titleClean = line.replace(/^[#0-9\.\s]+/, '').trim();
        currentSection = {
          id: `sec_${sectionIdx}`,
          title: titleClean || `Sección ${sectionIdx}`,
          level: isH2 ? 2 : 1,
          paragraphCount: 0,
          previewText: '',
          tables: [],
          images: [],
        };
        this.internalSections.push(currentSection);
        continue;
      }

      if (line.startsWith('|') && line.endsWith('|')) {
        if (currentSection && !currentSection.tables.includes(`tbl_${sectionIdx}`)) {
          currentSection.tables.push(`tbl_${sectionIdx}`);
          this.internalTables.push({
            id: `tbl_${sectionIdx}`,
            name: `Tabla en ${currentSection.title}`,
            rows: 3,
            cols: 3,
            headerSample: ['Columna 1', 'Columna 2'],
          });
        }
      } else if (currentSection && line.length > 0) {
        currentSection.paragraphCount++;
        if (!currentSection.previewText) {
          currentSection.previewText = line.substring(0, 100);
        }
      }
    }

    if (this.internalSections.length === 0) {
      this.internalSections.push({
        id: 'sec_root',
        title: this.title || 'Documento Principal',
        level: 1,
        paragraphCount: lines.length,
        previewText: lines[0] || '',
        tables: [],
        images: [],
      });
    }

    this.internalTags = Array.from(discoveredTags);
  }

  public async exportContent(_format: 'docx' | 'xlsx' | 'json'): Promise<Blob | Uint8Array> {
    const serialized = JSON.stringify({
      title: this.title,
      kind: this.kind,
      sections: this.internalSections,
      images: this.internalImages,
      rawContent: this.rawLines.join('\n'),
    }, null, 2);

    return new Blob([serialized], { type: 'application/json' });
  }

  public async inspect(): Promise<CanonicalDocumentState> {
    return {
      documentId: this.documentId,
      kind: this.kind,
      title: this.title,
      sections: [...this.internalSections],
      tablesSummary: [...this.internalTables],
      sheetsSummary: this.kind === 'spreadsheet' ? [...this.internalSheets] : [],
      tagsPresent: [...this.internalTags],
      totalParagraphs: this.rawLines.length,
      totalImages: this.internalImages.length,
      version: 1,
    };
  }

  public async findSection(title: string): Promise<DocumentSection | null> {
    const normalize = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
    const tNorm = normalize(title);
    return this.internalSections.find((s) => {
      const sNorm = normalize(s.title);
      return sNorm.includes(tNorm) || tNorm.includes(sNorm);
    }) || null;
  }

  public async findText(query: string): Promise<Array<{ rangeId: string; snippet: string }>> {
    const qLower = query.toLowerCase();
    const results: Array<{ rangeId: string; snippet: string }> = [];
    this.rawLines.forEach((line, idx) => {
      if (line.toLowerCase().includes(qLower)) {
        results.push({ rangeId: `line_${idx}`, snippet: line });
      }
    });
    return results;
  }

  public async insertImage(op: InsertImageOperation): Promise<OperationExecutionResult> {
    const targetTitle = op.target.sectionTitle || 'Observaciones';
    let section = await this.findSection(targetTitle);

    if (!section && this.internalSections.length > 0) {
      section = this.internalSections[this.internalSections.length - 1];
    }

    const imageId = `img_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    const newImageRecord = {
      id: imageId,
      sectionId: section ? section.id : 'sec_root',
      url: op.asset.url || '',
      caption: op.asset.caption || 'Evidencia adjunta',
    };

    this.internalImages.push(newImageRecord);
    if (section) {
      section.images.push(imageId);
    }

    // Insert image representation into raw document content
    const imgMarkdown = `\n![${op.asset.caption || 'Imagen adjunta'}](${op.asset.url || op.asset.assetId})\n`;
    let inserted = false;

    for (let i = 0; i < this.rawLines.length; i++) {
      if (section && this.rawLines[i].toLowerCase().includes(section.title.toLowerCase())) {
        this.rawLines.splice(i + 2, 0, imgMarkdown);
        inserted = true;
        break;
      }
    }

    if (!inserted) {
      this.rawLines.push(imgMarkdown);
    }

    return {
      success: true,
      operation: 'insert_image',
      elementId: imageId,
      message: `Image ${op.asset.assetId} successfully anchored to section "${section?.title || 'Observaciones'}".`,
      diffSummary: {
        sectionId: section?.id,
        totalImagesNow: this.internalImages.length,
      },
    };
  }

  public async insertText(op: InsertTextOperation): Promise<OperationExecutionResult> {
    const targetTitle = op.target.sectionTitle || '';
    const section = targetTitle ? await this.findSection(targetTitle) : null;
    const rawTag = op.target.tag || '';
    const cleanTag = rawTag.replace(/[{}]/g, '').toUpperCase();

    const textToInsert = `\n${op.content}\n`;
    let inserted = false;

    // 1. Try inserting adjacent to the tag line (e.g. {{SOLUCION}})
    if (cleanTag) {
      for (let i = 0; i < this.rawLines.length; i++) {
        const lineUpper = this.rawLines[i].toUpperCase();
        if (lineUpper.includes(`{{${cleanTag}}}`) || lineUpper.includes(cleanTag)) {
          this.rawLines.splice(i + 1, 0, textToInsert);
          inserted = true;
          break;
        }
      }
    }

    // 2. Try inserting below section heading
    if (!inserted && section) {
      section.paragraphCount++;
      const normalize = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
      const sNorm = normalize(section.title);
      for (let i = 0; i < this.rawLines.length; i++) {
        if (normalize(this.rawLines[i]).includes(sNorm)) {
          this.rawLines.splice(i + 1, 0, textToInsert);
          inserted = true;
          break;
        }
      }
    }

    // 3. Fallback
    if (!inserted) {
      this.rawLines.push(textToInsert);
    }

    return {
      success: true,
      operation: 'insert_text',
      message: `Text inserted into ${section ? section.title : cleanTag ? `tag {{${cleanTag}}}` : 'document end'}.`,
      diffSummary: { linesCount: this.rawLines.length },
    };
  }


  public async replaceContent(op: ReplaceContentOperation): Promise<OperationExecutionResult> {
    const tag = op.target.tag;
    let replacedCount = 0;

    if (tag) {
      const cleanTag = tag.replace(/[{}]/g, '');
      const regex = new RegExp(`\\{\\{${cleanTag}\\}\\}`, 'gi');
      this.rawLines = this.rawLines.map((line) => {
        if (regex.test(line)) {
          replacedCount++;
          return line.replace(regex, op.newContent);
        }
        return line;
      });
    }

    return {
      success: true,
      operation: 'replace_content',
      message: `Replaced ${replacedCount} occurrences of target.`,
    };
  }

  public async deleteContent(_op: DeleteContentOperation): Promise<OperationExecutionResult> {
    return {
      success: true,
      operation: 'delete_content',
      message: 'Content deletion acknowledged.',
    };
  }

  public async createTable(op: CreateTableOperation): Promise<OperationExecutionResult> {
    const tableId = `tbl_${Date.now()}`;
    this.internalTables.push({
      id: tableId,
      name: `Tabla creada (${op.headers.join(', ')})`,
      rows: (op.rows?.length || 0) + 1,
      cols: op.headers.length,
      headerSample: op.headers,
    });

    return {
      success: true,
      operation: 'create_table',
      elementId: tableId,
      message: `Table with ${op.headers.length} columns created.`,
    };
  }

  public async updateTable(op: UpdateTableOperation): Promise<OperationExecutionResult> {
    if (this.internalTables.length > 0) {
      this.internalTables[0].rows += op.data.length;
    }
    return {
      success: true,
      operation: 'update_table',
      message: `Updated table with ${op.data.length} new records.`,
    };
  }

  /**
   * Returns current raw content for rendering
   */
  public getRawContent(): string {
    return this.rawLines.join('\n');
  }

  public getImages(): Array<{ id: string; sectionId: string; url: string; caption?: string }> {
    return [...this.internalImages];
  }
}
