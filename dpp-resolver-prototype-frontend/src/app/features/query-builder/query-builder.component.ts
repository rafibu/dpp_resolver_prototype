import {Component, DestroyRef, inject, signal} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {MatAutocompleteModule, MatAutocompleteSelectedEvent} from '@angular/material/autocomplete';
import {MatButtonModule} from '@angular/material/button';
import {MatButtonToggleModule} from '@angular/material/button-toggle';
import {MatCardModule} from '@angular/material/card';
import {MatChipInputEvent, MatChipsModule} from '@angular/material/chips';
import {MatDividerModule} from '@angular/material/divider';
import {MatFormFieldModule} from '@angular/material/form-field';
import {MatIconModule} from '@angular/material/icon';
import {MatInputModule} from '@angular/material/input';
import {MatProgressBarModule} from '@angular/material/progress-bar';
import {MatSelectModule} from '@angular/material/select';
import {MatTableModule} from '@angular/material/table';
import {MatTooltipModule} from '@angular/material/tooltip';
import {finalize, take} from 'rxjs';
import {FederationService} from '../../core/federation.service';
import {ResolverService} from '../../core/resolver.service';
import {QueryService} from '../../core/query.service';
import {QueryMetadataService} from '../../core/query-metadata.service';
import {toErrorMessage} from '../../core/http-error.utils';
import {PlatformInfo} from '../../core/models/federation.model';
import {
  LIST_OPERATORS,
  PredicateFilter,
  PredicateOperator,
  PredicateQueryRequest,
  PredicateQueryResponse,
  QueryExecutionMode,
  QueryParameterMetadata,
  QueryResultMode,
  QueryValueType,
  SubjectTypeMetadata,
  TraverseQueryRequest,
  TraverseQueryResponse,
  VALUE_LESS_OPERATORS
} from '../../core/models/query.model';

type QueryType = 'predicate' | 'traverse';

interface FilterRow {
  path: string;
  valueType: QueryValueType;
  enumValues: unknown[];
  operators: PredicateOperator[];
  operator: PredicateOperator;
  textValue: unknown;
  boolValue: boolean;
  inValues: unknown[];
}

interface SourceRow {
  subjectType: string;
  referencePaths: string[];
}

interface ResultView {
  category: 'predicate' | 'traverse';
  resultMode?: QueryResultMode;
  durationMs: number;
  count: number | null;
  aggregate: number | null;
  matchCount: number | null;
  columns: string[];
  rows: Record<string, unknown>[];
  raw: unknown;
}

@Component({
  selector: 'app-query-builder',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatAutocompleteModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatCardModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatTableModule,
    MatTooltipModule
  ],
  templateUrl: './query-builder.component.html',
  styleUrl: './query-builder.component.scss'
})
export class QueryBuilderComponent {
  private federationService = inject(FederationService);
  private resolverService = inject(ResolverService);
  private queryService = inject(QueryService);
  private metadataService = inject(QueryMetadataService);
  private destroyRef = inject(DestroyRef);

  public readonly QueryResultMode = QueryResultMode;
  public readonly QueryExecutionMode = QueryExecutionMode;
  public readonly PredicateOperator = PredicateOperator;

  /** Selectable value types when filtering on a path the metadata doesn't describe. */
  public readonly valueTypes: QueryValueType[] = ['TEXT', 'NUMBER', 'BOOLEAN', 'DATE', 'ENUM', 'REFERENCE'];

  public platforms = this.federationService.platforms;
  public platformId = signal<string | null>(null);

  public queryType: QueryType = 'predicate';

  // Predicate form
  public resultMode: QueryResultMode = QueryResultMode.SELECT;
  public executionMode: QueryExecutionMode = QueryExecutionMode.INDEXED;
  public subjectTypes: string[] = [];
  public filters: FilterRow[] = [];
  public returnFields: string[] = [];
  public returnFieldInput = '';
  public aggregatePath = '';
  public predicateMetadata = signal<SubjectTypeMetadata | null>(null);

  // Traverse form
  public traverseExecutionMode: QueryExecutionMode = QueryExecutionMode.INDEXED;
  public traverseSubjectType = '';
  public dppId = '';
  public revisionNumber: number | null = null;
  public sources: SourceRow[] = [{subjectType: '', referencePaths: []}];
  public sourceMetadata = signal<Record<string, SubjectTypeMetadata>>({});

  // Execution state
  public running = signal(false);
  public error = signal<string | null>(null);
  public result = signal<ResultView | null>(null);

  constructor() {
    // Default-select the first running platform so the form is usable immediately.
    const platforms = this.platforms();
    const initial = platforms.find(platform => platform.status === 'RUNNING') ?? platforms[0];
    if (initial) {
      this.platformId.set(initial.platform_id);
      this.onPlatformChange(initial.platform_id);
    }
  }

  // -------------------------------------------------------------------------
  // Platform / subject-type context
  // -------------------------------------------------------------------------

  public selectedPlatform(): PlatformInfo | null {
    return this.platforms().find(platform => platform.platform_id === this.platformId()) ?? null;
  }

  public platformUrl(): string | null {
    return this.selectedPlatform()?.external_url ?? null;
  }

  public availableSubjectTypes(): string[] {
    return [...(this.selectedPlatform()?.subject_types ?? [])].sort();
  }

  public onPlatformChange(platformId: string): void {
    this.platformId.set(platformId);
    this.result.set(null);
    this.error.set(null);
    const available = new Set(this.availableSubjectTypes());
    this.subjectTypes = this.subjectTypes.filter(subjectType => available.has(subjectType));
    this.loadPredicateMetadata(this.metadataSubjectType());
  }

  public setQueryType(type: QueryType): void {
    this.queryType = type;
    this.result.set(null);
    this.error.set(null);
  }

  // -------------------------------------------------------------------------
  // Predicate builder
  // -------------------------------------------------------------------------

  public onSubjectTypeChange(subjectType: string): void {
    this.onSubjectTypesChange(subjectType ? [subjectType] : []);
  }

  public onSubjectTypesChange(subjectTypes: string[]): void {
    this.subjectTypes = [...subjectTypes];
    this.returnFields = [];
    this.returnFieldInput = '';
    this.aggregatePath = '';
    this.filters = [];
    this.loadPredicateMetadata(this.metadataSubjectType());
  }

  public predicateParameters(): QueryParameterMetadata[] {
    return this.predicateMetadata()?.predicateParameters ?? [];
  }

  public numericParameters(): QueryParameterMetadata[] {
    return this.predicateParameters().filter(parameter => parameter.valueType === 'NUMBER');
  }

  public addFilter(): void {
    const first = this.predicateParameters()[0];
    const row: FilterRow = {
      path: '',
      valueType: 'TEXT',
      enumValues: [],
      operators: this.metadataService.operatorsForValueType('TEXT'),
      operator: PredicateOperator.EQ,
      textValue: '',
      boolValue: true,
      inValues: []
    };
    this.filters = [...this.filters, row];
    if (first) {
      this.onFilterPathChange(row, first.path);
    }
  }

  public removeFilter(row: FilterRow): void {
    this.filters = this.filters.filter(filter => filter !== row);
  }

  public onFilterPathChange(row: FilterRow, path: string): void {
    row.path = path;
    const parameter = this.predicateParameters().find(candidate => candidate.path === path);
    // Known paths adopt the schema/fallback value type; unknown (free-typed) paths
    // keep the user's current type so any field can be filtered. Suggestions guide,
    // they don't constrain.
    const valueType = parameter?.valueType ?? row.valueType;
    this.applyFilterValueType(row, valueType, parameter?.enumValues ?? [], parameter?.operators);
  }

  public onFilterValueTypeChange(row: FilterRow, valueType: QueryValueType): void {
    if (valueType === row.valueType) {
      return;
    }
    this.applyFilterValueType(row, valueType, [], undefined);
  }

  /** Apply a value type to a filter row, refreshing operators and clearing stale values. */
  private applyFilterValueType(
    row: FilterRow,
    valueType: QueryValueType,
    enumValues: unknown[],
    operators?: PredicateOperator[]
  ): void {
    const typeChanged = valueType !== row.valueType;
    row.valueType = valueType;
    row.enumValues = enumValues;
    row.operators = operators ?? this.metadataService.operatorsForValueType(valueType);
    if (!row.operators.includes(row.operator)) {
      row.operator = row.operators[0];
    }
    if (typeChanged) {
      row.textValue = '';
      row.boolValue = true;
      row.inValues = [];
    }
  }

  public onFilterOperatorChange(row: FilterRow, operator: PredicateOperator): void {
    row.operator = operator;
  }

  // -------------------------------------------------------------------------
  // Return fields (SELECT) — free-form with metadata-driven suggestions
  // -------------------------------------------------------------------------

  public addReturnField(event: MatChipInputEvent): void {
    this.appendReturnField(event.value);
    event.chipInput?.clear();
    this.returnFieldInput = '';
  }

  public addReturnFieldFromOption(event: MatAutocompleteSelectedEvent): void {
    this.appendReturnField(event.option.value);
    this.returnFieldInput = '';
  }

  public removeReturnField(field: string): void {
    this.returnFields = this.returnFields.filter(existing => existing !== field);
  }

  private appendReturnField(value: string): void {
    const field = (value ?? '').trim();
    if (field && !this.returnFields.includes(field)) {
      this.returnFields = [...this.returnFields, field];
    }
  }

  public needsValueInput(row: FilterRow): boolean {
    return !VALUE_LESS_OPERATORS.has(row.operator);
  }

  public isListOperator(operator: PredicateOperator): boolean {
    return LIST_OPERATORS.has(operator);
  }

  // -------------------------------------------------------------------------
  // Traverse builder
  // -------------------------------------------------------------------------

  public addSource(): void {
    this.sources = [...this.sources, {subjectType: '', referencePaths: []}];
  }

  public removeSource(row: SourceRow): void {
    this.sources = this.sources.filter(source => source !== row);
  }

  public onSourceSubjectTypeChange(row: SourceRow, subjectType: string): void {
    row.subjectType = subjectType;
    row.referencePaths = [];
    this.loadSourceMetadata(subjectType);
  }

  public referencePathsFor(subjectType: string): string[] {
    return (this.sourceMetadata()[subjectType]?.referencePaths ?? []).map(reference => reference.referencePath);
  }

  // -------------------------------------------------------------------------
  // Request construction + validation
  // -------------------------------------------------------------------------

  public buildPredicateRequest(): PredicateQueryRequest | null {
    const request: PredicateQueryRequest = {
      result_mode: this.resultMode,
      execution_mode: this.executionMode,
      filters: this.filters
        .filter(row => !!row.path)
        .map(row => this.toFilter(row))
    };
    if (this.subjectTypes.length) {
      request.subject_types = [...this.subjectTypes];
    }
    if (this.resultMode === QueryResultMode.SELECT && this.returnFields.length) {
      request.return_fields = [...this.returnFields];
    }
    if (this.resultMode === QueryResultMode.SUM && this.aggregatePath) {
      request.aggregate_path = this.aggregatePath;
    }
    return request;
  }

  public buildTraverseRequest(): TraverseQueryRequest | null {
    if (!this.traverseSubjectType || !this.dppId) {
      return null;
    }
    const request: TraverseQueryRequest = {
      execution_mode: this.traverseExecutionMode,
      subject_type: this.traverseSubjectType,
      dpp_id: this.dppId,
      sources: this.sources
        .filter(source => !!source.subjectType)
        .map(source => source.referencePaths.length
          ? {subject_type: source.subjectType, reference_paths: [...source.referencePaths]}
          : {subject_type: source.subjectType})
    };
    if (this.revisionNumber != null && `${this.revisionNumber}` !== '') {
      request.revision_number = Number(this.revisionNumber);
    }
    return request;
  }

  private toFilter(row: FilterRow): PredicateFilter {
    const filter: PredicateFilter = {path: row.path, operator: row.operator};
    if (VALUE_LESS_OPERATORS.has(row.operator)) {
      return filter;
    }
    if (this.isListOperator(row.operator)) {
      const raw = row.valueType === 'ENUM' ? row.inValues : splitList(row.textValue);
      filter.value = raw.map(value => parseFilterValue(row.valueType, value));
      return filter;
    }
    if (row.valueType === 'BOOLEAN') {
      filter.value = row.boolValue;
      return filter;
    }
    if (row.valueType === 'NUMBER') {
      filter.value = parseFilterValue(row.valueType, row.textValue);
      return filter;
    }
    filter.value = parseFilterValue(row.valueType, row.textValue);
    return filter;
  }

  public filterError(row: FilterRow): string | null {
    if (!row.path) {
      return 'Select a parameter.';
    }
    if (VALUE_LESS_OPERATORS.has(row.operator)) {
      return null;
    }
    if (this.isListOperator(row.operator)) {
      const raw = row.valueType === 'ENUM' ? row.inValues : splitList(row.textValue);
      if (!raw.length) {
        return 'Enter at least one value.';
      }
      if (row.valueType === 'NUMBER' && raw.some(value => !isNumeric(value))) {
        return 'All values must be numeric.';
      }
      if (row.valueType === 'DATE' && raw.some(value => !isIsoDate(value))) {
        return 'All values must be ISO dates or date-times.';
      }
      if (row.valueType === 'ENUM' && !allEnumValuesAreAllowed(raw, row.enumValues)) {
        return 'Select values from the available enum options.';
      }
      return null;
    }
    if (row.valueType === 'BOOLEAN') {
      return null;
    }
    if (row.valueType === 'NUMBER') {
      return isNumeric(row.textValue) ? null : 'Enter a numeric value.';
    }
    if (row.valueType === 'DATE') {
      return isIsoDate(row.textValue) ? null : 'Enter an ISO date or date-time.';
    }
    if (row.valueType === 'ENUM') {
      if (isBlank(row.textValue)) {
        return 'Select a value.';
      }
      return enumValueIsAllowed(row.textValue, row.enumValues) ? null : 'Select a value from the available enum options.';
    }
    return isBlank(row.textValue) ? 'Enter a value.' : null;
  }

  public isPredicateValid(): boolean {
    if (this.filters.some(row => this.filterError(row) !== null)) {
      return false;
    }
    if (this.resultMode === QueryResultMode.SUM) {
      // Any non-blank path is allowed; the numeric parameters are suggestions only.
      return !isBlank(this.aggregatePath);
    }
    return true;
  }

  public traverseError(): string | null {
    if (!this.traverseSubjectType) {
      return 'Target subject type is required.';
    }
    if (!this.dppId) {
      return 'Target DPP id is required.';
    }
    if (this.revisionNumber != null && `${this.revisionNumber}` !== '') {
      if (!isNumeric(this.revisionNumber) || Number(this.revisionNumber) <= 0 || !Number.isInteger(Number(this.revisionNumber))) {
        return 'Revision number must be a positive integer.';
      }
    }
    const sources = this.sources.filter(source => !!source.subjectType);
    if (!sources.length) {
      return 'Add at least one source with a subject type.';
    }
    return null;
  }

  public isTraverseValid(): boolean {
    return this.traverseError() === null;
  }

  public isValid(): boolean {
    return this.queryType === 'predicate' ? this.isPredicateValid() : this.isTraverseValid();
  }

  public previewJson(): string {
    const request = this.queryType === 'predicate' ? this.buildPredicateRequest() : this.buildTraverseRequest();
    return request ? JSON.stringify(request, null, 2) : '{}';
  }

  // -------------------------------------------------------------------------
  // Execution
  // -------------------------------------------------------------------------

  public execute(): void {
    const platformUrl = this.platformUrl();
    if (!platformUrl || !this.isValid()) {
      return;
    }
    this.running.set(true);
    this.error.set(null);
    this.result.set(null);

    if (this.queryType === 'predicate') {
      const request = this.buildPredicateRequest()!;
      this.queryService.executePredicate(platformUrl, request).pipe(
        take(1),
        finalize(() => this.running.set(false))
      ).subscribe({
        next: execution => this.result.set(this.toPredicateView(request, execution.response, execution.durationMs)),
        error: err => this.error.set(toErrorMessage(err, 'Predicate query failed'))
      });
    } else {
      const request = this.buildTraverseRequest()!;
      this.queryService.executeTraverse(platformUrl, request).pipe(
        take(1),
        finalize(() => this.running.set(false))
      ).subscribe({
        next: execution => this.result.set(this.toTraverseView(execution.response, execution.durationMs)),
        error: err => this.error.set(toErrorMessage(err, 'Traverse query failed'))
      });
    }
  }

  private toPredicateView(request: PredicateQueryRequest, response: PredicateQueryResponse, durationMs: number): ResultView {
    const matches = Array.isArray(response.matches) ? response.matches as Record<string, unknown>[] : [];
    return {
      category: 'predicate',
      resultMode: request.result_mode,
      durationMs,
      count: response.count ?? null,
      aggregate: response.aggregate ?? null,
      matchCount: matches.length,
      columns: columnsOf(matches),
      rows: matches,
      raw: response
    };
  }

  private toTraverseView(response: TraverseQueryResponse, durationMs: number): ResultView {
    // The Java traverse endpoint returns the matching source documents/facts for
    // this platform; there is no structured edge object in the response.
    const matches = Array.isArray(response.matches) ? response.matches as Record<string, unknown>[] : [];
    return {
      category: 'traverse',
      durationMs,
      count: null,
      aggregate: null,
      matchCount: matches.length,
      columns: columnsOf(matches),
      rows: matches,
      raw: response
    };
  }

  public rawResultJson(): string {
    const result = this.result();
    return result ? JSON.stringify(result.raw, null, 2) : '';
  }

  public cell(row: Record<string, unknown>, column: string): string {
    const value = row[column];
    if (value == null) {
      return '';
    }
    return typeof value === 'object' ? JSON.stringify(value) : String(value);
  }

  // -------------------------------------------------------------------------
  // Metadata loading (schema-derived, falling back to local metadata)
  // -------------------------------------------------------------------------

  private loadPredicateMetadata(subjectType: string): void {
    if (!subjectType) {
      this.predicateMetadata.set(null);
      return;
    }
    this.predicateMetadata.set(this.metadataService.fallbackMetadata(subjectType));
    const resolverUrl = this.federationService.resolverUrl();
    if (!resolverUrl) {
      return;
    }
    this.resolverService.listSchemasForSubjectType(resolverUrl, subjectType).pipe(
      take(1)
    ).subscribe({
      next: schemas => {
        const latest = schemas.at(-1)?.schema;
        if (latest) {
          this.predicateMetadata.set(this.metadataService.getMetadata(subjectType, latest));
        }
      },
      error: () => { /* keep fallback metadata */ }
    });
  }

  private metadataSubjectType(): string {
    return this.subjectTypes[0] ?? this.availableSubjectTypes()[0] ?? '';
  }

  private loadSourceMetadata(subjectType: string): void {
    if (!subjectType || this.sourceMetadata()[subjectType]) {
      return;
    }
    this.sourceMetadata.update(current => ({...current, [subjectType]: this.metadataService.fallbackMetadata(subjectType)}));
    const resolverUrl = this.federationService.resolverUrl();
    if (!resolverUrl) {
      return;
    }
    this.resolverService.listSchemasForSubjectType(resolverUrl, subjectType).pipe(
      take(1)
    ).subscribe({
      next: schemas => {
        const latest = schemas.at(-1)?.schema;
        if (latest) {
          this.sourceMetadata.update(current => ({...current, [subjectType]: this.metadataService.getMetadata(subjectType, latest)}));
        }
      },
      error: () => { /* keep fallback metadata */ }
    });
  }
}

function splitList(value: unknown): string[] {
  return String(value ?? '')
    .split(/[,\n]/)
    .map(entry => entry.trim())
    .filter(entry => entry.length > 0);
}

function isNumeric(value: unknown): boolean {
  if (typeof value === 'number') {
    return Number.isFinite(value);
  }
  const text = String(value).trim();
  return text !== '' && Number.isFinite(Number(text));
}

function parseFilterValue(valueType: QueryValueType, raw: unknown): unknown {
  switch (valueType) {
    case 'NUMBER':
      return Number(raw);
    case 'BOOLEAN':
      return raw === true || raw === 'true';
    case 'DATE':
    case 'TEXT':
    case 'REFERENCE':
      return String(raw ?? '').trim();
    case 'ENUM':
    default:
      // Values selected from MatSelect retain their JSON-Schema scalar type.
      return raw;
  }
}

function isBlank(value: unknown): boolean {
  return String(value ?? '').trim() === '';
}

function enumValueIsAllowed(value: unknown, available: unknown[]): boolean {
  return available.length === 0 || available.some(candidate => Object.is(candidate, value));
}

function allEnumValuesAreAllowed(values: unknown[], available: unknown[]): boolean {
  return available.length === 0 || values.every(value => enumValueIsAllowed(value, available));
}

function isIsoDate(value: unknown): boolean {
  const text = String(value ?? '').trim();
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (dateMatch) {
    const [year, month, day] = dateMatch.slice(1).map(Number);
    const parsed = new Date(Date.UTC(year, month - 1, day));
    return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
  }
  // Require a timezone for date-time values so lexical comparisons stay in a
  // single, explicit temporal frame on both generic platform implementations.
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(text)) {
    return false;
  }
  return isIsoDate(text.slice(0, 10)) && Number.isFinite(Date.parse(text));
}

function columnsOf(rows: Record<string, unknown>[]): string[] {
  const columns: string[] = [];
  for (const row of rows) {
    if (row && typeof row === 'object') {
      for (const key of Object.keys(row)) {
        if (!columns.includes(key)) {
          columns.push(key);
        }
      }
    }
  }
  return columns;
}
