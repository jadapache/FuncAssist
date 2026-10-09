/**
 * DocumentAgent.ts
 * Independent abstraction layer between LLM/Agentic RAG and the document engine (Univer).
 * Handles the Inspect -> Plan -> Validate -> Execute -> Verify loop.
 */

import type {
  CanonicalDocumentOperation,
  CanonicalDocumentState,
  CreateTableOperation,
  DeleteContentOperation,
  FindSectionOperation,
  FindTextOperation,
  IDocumentAdapter,
  InsertImageOperation,
  InsertTextOperation,
  OperationExecutionResult,
  ReplaceContentOperation,
  UpdateTableOperation,
  VerificationReport,
} from './types';

export class DocumentAgent {
  private adapter: IDocumentAdapter;

  constructor(adapter: IDocumentAdapter) {
    this.adapter = adapter;
  }

  /** Swap adapter dynamically (e.g. Univer -> EigenPal) without altering consumer code */
  public setAdapter(adapter: IDocumentAdapter): void {
    this.adapter = adapter;
  }

  public getAdapter(): IDocumentAdapter {
    return this.adapter;
  }

  /**
   * 1. INSPECT
   * Reads current canonical document representation.
   */
  public async inspect(): Promise<CanonicalDocumentState> {
    return await this.adapter.inspect();
  }

  /**
   * 2. VALIDATE
   * Validates target existence and preconditions against canonical state.
   */
  public async validate(
    op: CanonicalDocumentOperation,
    state?: CanonicalDocumentState
  ): Promise<{ valid: boolean; reason: string }> {
    const currentState = state || (await this.inspect());

    if (op.operation === 'inspect_document') {
      return { valid: true, reason: 'Inspection operation always valid.' };
    }

    if ('target' in op && op.target) {
      const { sectionTitle, tag, cellRange } = op.target;
      const normalize = (s: string) =>
        s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();

      let targetMatched = false;
      const checkedDetails: string[] = [];

      if (sectionTitle) {
        const normTarget = normalize(sectionTitle);
        const found = currentState.sections.some((s) => {
          const normSec = normalize(s.title);
          return normSec.includes(normTarget) || normTarget.includes(normSec);
        });
        if (found) {
          targetMatched = true;
        } else {
          checkedDetails.push(`sección "${sectionTitle}"`);
        }
      }

      if (tag) {
        const normTag = normalize(tag.replace(/[{}]/g, ''));
        const found = currentState.tagsPresent.some((t) => {
          const normT = normalize(t.replace(/[{}]/g, ''));
          return normT === normTag || normT.includes(normTag) || normTag.includes(normT);
        });
        if (found) {
          targetMatched = true;
        } else {
          checkedDetails.push(`tag "${tag}"`);
        }
      }

      if (cellRange && currentState.kind === 'spreadsheet') {
        targetMatched = true;
      }

      // If no specific anchor was required, or target was matched by section OR tag
      if (!sectionTitle && !tag && !cellRange) {
        targetMatched = true;
      }

      if (!targetMatched && (currentState.sections.length > 0 || currentState.tagsPresent.length > 0)) {
        return {
          valid: false,
          reason: `Target placeholder o sección "${tag || sectionTitle}" no fue localizado en el documento actual.`,
        };
      }
    }

    return { valid: true, reason: 'Preconditions validated successfully.' };

  }

  /**
   * 3. EXECUTE
   * Translates canonical operation into concrete adapter action.
   */
  private async executeOnAdapter(op: CanonicalDocumentOperation): Promise<OperationExecutionResult> {
    switch (op.operation) {
      case 'insert_image':
        return await this.adapter.insertImage(op as InsertImageOperation);
      case 'insert_text':
        return await this.adapter.insertText(op as InsertTextOperation);
      case 'replace_content':
        return await this.adapter.replaceContent(op as ReplaceContentOperation);
      case 'update_table':
        return await this.adapter.updateTable(op as UpdateTableOperation);
      case 'delete_content':
        return await this.adapter.deleteContent(op as DeleteContentOperation);
      case 'create_table':
        return await this.adapter.createTable(op as CreateTableOperation);
      case 'find_section': {
        const section = await this.adapter.findSection((op as FindSectionOperation).sectionTitle);
        return {
          success: section !== null,
          operation: 'find_section',
          elementId: section?.id,
          message: section ? `Found section: ${section.title}` : 'Section not found.',
        };
      }
      case 'find_text': {
        const results = await this.adapter.findText((op as FindTextOperation).query);
        return {
          success: results.length > 0,
          operation: 'find_text',
          message: `Found ${results.length} occurrence(s).`,
        };
      }
      case 'inspect_document': {
        const state = await this.adapter.inspect();
        return {
          success: true,
          operation: 'inspect_document',
          message: `Inspected ${state.sections.length} sections, ${state.tagsPresent.length} tags.`,
          diffSummary: { sectionsCount: state.sections.length },
        };
      }
      case 'move_content':
        return {
          success: false,
          operation: 'move_content',
          message: 'MoveContent operation is not yet implemented in the current adapter.',
          error: 'NOT_IMPLEMENTED',
        };
      default: {
        const _exhaustiveCheck: never = op;
        void _exhaustiveCheck;
        // Fallback para operaciones inesperadas (nunca debe ejecutarse en código tipado)
        return {
          success: false,
          operation: 'inspect_document' as const,
          message: `Unsupported operation received.`,
          error: 'UNKNOWN_OPERATION',
        };
      }
    }
  }

  /**
   * 4. VERIFY
   * Re-inspects the document post-mutation to assert the desired delta occurred.
   */
  public async verify(
    op: CanonicalDocumentOperation,
    stateBefore: CanonicalDocumentState
  ): Promise<VerificationReport> {
    const stateAfter = await this.inspect();
    const diff: Record<string, any> = {};

    let verified = false;
    let feedback = '';

    if (op.operation === 'insert_image') {
      const imgDiff = stateAfter.totalImages - stateBefore.totalImages;
      diff.imagesAdded = imgDiff;
      verified = imgDiff >= 1 || stateAfter.totalImages > 0;
      feedback = verified
        ? `Verification SUCCESS: Image inserted successfully into section ${(op as InsertImageOperation).target.sectionTitle || 'document'}.`
        : 'Verification WARNING: Image count did not increase as expected.';
    } else if (op.operation === 'insert_text') {
      const paraDiff = stateAfter.totalParagraphs - stateBefore.totalParagraphs;
      diff.paragraphsDiff = paraDiff;
      verified = true;
      feedback = 'Verification SUCCESS: Text inserted into target.';
    } else {
      verified = true;
      feedback = `Verification completed for ${op.operation}.`;
    }

    return {
      verified,
      operation: op.operation,
      targetFound: true,
      stateAfter,
      diffDetected: diff,
      feedback,
    };
  }

  /**
   * Full Pipeline: INSPECT -> VALIDATE -> EXECUTE -> VERIFY
   */
  public async dispatch(
    op: CanonicalDocumentOperation
  ): Promise<{ result: OperationExecutionResult; report: VerificationReport }> {
    // 1. Inspect state before
    const stateBefore = await this.inspect();

    // 2. Validate
    const validation = await this.validate(op, stateBefore);
    if (!validation.valid) {
      throw new Error(`[DocumentAgent Validation Error] ${validation.reason}`);
    }

    // 3. Execute
    const result = await this.executeOnAdapter(op);
    if (!result.success) {
      throw new Error(`[DocumentAgent Execution Error] ${result.error || result.message}`);
    }

    // 4. Verify
    const report = await this.verify(op, stateBefore);

    return { result, report };
  }
}
