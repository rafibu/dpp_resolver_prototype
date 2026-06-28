import {Injectable} from '@angular/core';
import {
  PredicateOperator,
  QueryParameterMetadata,
  QueryValueType,
  ReferencePathMetadata,
  SubjectTypeMetadata
} from './models/query.model';

/**
 * Supplies the query builder with the selectable predicate parameters and
 * reference paths for a subject type, so users are guided towards well-formed
 * queries instead of typing arbitrary paths.
 *
 * There is no dedicated backend query-metadata endpoint in this project, so this
 * service derives metadata in two layers:
 *
 *  1. {@link deriveFromSchema} traverses a JSON Schema (obtainable through
 *     `ResolverService.getSchema` / `listSchemasForSubjectType`) into
 *     dot-separated scalar paths, classifies each value type, collects enum
 *     values, and detects DPP-reference-shaped objects.
 *  2. {@link FALLBACK_METADATA} is a clearly-marked, NON-authoritative local
 *     provider with S4-compatible metadata, used when no schema is available or
 *     a schema is too permissive to yield useful paths. It is isolated here so a
 *     real backend metadata source can replace it later.
 */
@Injectable({
  providedIn: 'root'
})
export class QueryMetadataService {
  /**
   * Resolve metadata for a subject type. A schema (when supplied) is preferred;
   * otherwise — or when the schema yields no usable parameters — the local
   * fallback is returned.
   */
  getMetadata(subjectType: string, schema?: unknown): SubjectTypeMetadata {
    if (schema) {
      const derived = this.deriveFromSchema(subjectType, schema);
      if (derived.predicateParameters.length > 0 || derived.referencePaths.length > 0) {
        return derived;
      }
    }
    return this.fallbackMetadata(subjectType);
  }

  /** S4-compatible local fallback. Marked as non-authoritative via `isFallback`. */
  fallbackMetadata(subjectType: string): SubjectTypeMetadata {
    const entry = FALLBACK_METADATA[subjectType];
    const predicateParameters = (entry?.parameters ?? GENERIC_FALLBACK_PARAMETERS).map(parameter =>
      this.toParameter(subjectType, parameter));
    const referencePaths = (entry?.references ?? []).map(reference => ({
      sourceSubjectType: subjectType,
      ...reference
    }));
    return {subjectType, predicateParameters, referencePaths, isFallback: true};
  }

  /** Operators valid for a value type, following the Java `PredicateOperator` enum. */
  operatorsForValueType(valueType: QueryValueType): PredicateOperator[] {
    switch (valueType) {
      case 'NUMBER':
        return [
          PredicateOperator.EQ, PredicateOperator.NEQ, PredicateOperator.EXISTS,
          PredicateOperator.NOT_EXISTS, PredicateOperator.IN, PredicateOperator.GT,
          PredicateOperator.GTE, PredicateOperator.LT, PredicateOperator.LTE
        ];
      case 'DATE':
        return [
          PredicateOperator.EQ, PredicateOperator.NEQ, PredicateOperator.EXISTS,
          PredicateOperator.NOT_EXISTS, PredicateOperator.IN, PredicateOperator.GT,
          PredicateOperator.GTE, PredicateOperator.LT, PredicateOperator.LTE
        ];
      case 'BOOLEAN':
        return [
          PredicateOperator.EQ, PredicateOperator.NEQ,
          PredicateOperator.EXISTS, PredicateOperator.NOT_EXISTS
        ];
      case 'ENUM':
      case 'REFERENCE':
      case 'TEXT':
      default:
        return [
          PredicateOperator.EQ, PredicateOperator.NEQ, PredicateOperator.EXISTS,
          PredicateOperator.NOT_EXISTS, PredicateOperator.IN
        ];
    }
  }

  /**
   * Traverse a JSON Schema into selectable predicate parameters and reference
   * paths. Scalar leaves become dot-separated paths; objects shaped like a DPP
   * reference (a `$ref` property or an `x-dpp-reference` marker) become
   * reference paths.
   */
  deriveFromSchema(subjectType: string, schema: unknown): SubjectTypeMetadata {
    const parameters: QueryParameterMetadata[] = [];
    const references: ReferencePathMetadata[] = [];
    this.walk(subjectType, schema, '', parameters, references);
    return {subjectType, predicateParameters: parameters, referencePaths: references};
  }

  private walk(
    subjectType: string,
    node: unknown,
    path: string,
    parameters: QueryParameterMetadata[],
    references: ReferencePathMetadata[]
  ): void {
    if (!node || typeof node !== 'object') {
      return;
    }
    const schema = node as Record<string, any>;
    const properties = schema['properties'];
    if (!properties || typeof properties !== 'object') {
      return;
    }
    const required = new Set<string>(Array.isArray(schema['required']) ? schema['required'] : []);

    for (const [key, rawChild] of Object.entries(properties)) {
      const child = rawChild as Record<string, any>;
      const childPath = path ? `${path}.${key}` : key;

      if (this.isReferenceShaped(child)) {
        references.push({
          sourceSubjectType: subjectType,
          referencePath: childPath,
          targetSubjectType: child['x-dpp-reference'],
          label: humanize(childPath)
        });
        parameters.push(this.toParameter(subjectType, {
          path: `${childPath}.$ref`,
          valueType: 'REFERENCE',
          label: `${humanize(childPath)} reference`,
          description: 'Filter on the reference target string ($ref).'
        }));
        continue;
      }

      const type = normalizeType(child['type']);
      if (type === 'object' || child['properties']) {
        this.walk(subjectType, child, childPath, parameters, references);
        continue;
      }
      if (type === 'array') {
        continue; // Java predicate facts are scalar projections.
      }

      const valueType = this.classify(child, type);
      parameters.push(this.toParameter(subjectType, {
        path: childPath,
        valueType,
        label: humanize(childPath),
        required: required.has(key),
        enumValues: Array.isArray(child['enum']) ? [...child['enum']] : undefined
      }));
    }
  }

  private isReferenceShaped(child: Record<string, any>): boolean {
    if (child['x-dpp-reference']) {
      return true;
    }
    const childProperties = child['properties'];
    return !!childProperties && typeof childProperties === 'object' && '$ref' in childProperties;
  }

  private classify(child: Record<string, any>, type: string | undefined): QueryValueType {
    if (Array.isArray(child['enum']) && child['enum'].length > 0) {
      return 'ENUM';
    }
    if (type === 'integer' || type === 'number') {
      return 'NUMBER';
    }
    if (type === 'boolean') {
      return 'BOOLEAN';
    }
    const format = child['format'];
    if (type === 'string' && (format === 'date' || format === 'date-time')) {
      return 'DATE';
    }
    return 'TEXT';
  }

  private toParameter(subjectType: string, partial: PartialParameter): QueryParameterMetadata {
    return {
      subjectType,
      path: partial.path,
      label: partial.label ?? humanize(partial.path),
      valueType: partial.valueType,
      operators: this.operatorsForValueType(partial.valueType),
      enumValues: partial.enumValues,
      required: partial.required,
      description: partial.description
    };
  }
}

interface PartialParameter {
  path: string;
  valueType: QueryValueType;
  label?: string;
  enumValues?: unknown[];
  required?: boolean;
  description?: string;
}

function normalizeType(type: unknown): string | undefined {
  if (Array.isArray(type)) {
    return type.find(entry => entry !== 'null') ?? type[0];
  }
  return typeof type === 'string' ? type : undefined;
}

function humanize(path: string): string {
  return path
    .split('.')
    .map(segment => segment.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase()))
    .join(' › ');
}

interface FallbackEntry {
  parameters: PartialParameter[];
  references?: Omit<ReferencePathMetadata, 'sourceSubjectType'>[];
}

const GENERIC_FALLBACK_PARAMETERS: PartialParameter[] = [
  {path: 'serial_number', valueType: 'TEXT', label: 'Serial number'},
  {path: 'manufacturer', valueType: 'TEXT', label: 'Manufacturer'},
  {path: 'model', valueType: 'TEXT', label: 'Model'},
  {path: 'production_year', valueType: 'NUMBER', label: 'Production year'},
  {path: 'production_country', valueType: 'TEXT', label: 'Production country'},
  {path: 'quality_score', valueType: 'NUMBER', label: 'Quality score'}
];

/**
 * NON-AUTHORITATIVE fallback metadata aligned with the deterministic S4 dataset
 * (`dpp-workload-generator/src/workload/scenarios/s4.py`). Replace with backend
 * metadata when an endpoint becomes available.
 */
const FALLBACK_METADATA: Record<string, FallbackEntry> = {
  pv_module: {
    parameters: [
      ...GENERIC_FALLBACK_PARAMETERS,
      {path: 'nominal_power_w', valueType: 'NUMBER', label: 'Nominal power (W)'},
      {path: 'contains_lead', valueType: 'BOOLEAN', label: 'Contains lead'},
      {path: 'lead_mass_kg', valueType: 'NUMBER', label: 'Lead mass (kg)'},
      {path: 'silver_mass_g', valueType: 'NUMBER', label: 'Silver mass (g)'},
      {path: 'hazardous_substance_flag', valueType: 'BOOLEAN', label: 'Hazardous substance'},
      {path: 'operational_status', valueType: 'ENUM', label: 'Operational status', enumValues: ['active', 'recycled']},
      {path: 'disposal_status', valueType: 'ENUM', label: 'Disposal status', enumValues: ['active', 'recycled']},
      {path: 'disposal_date', valueType: 'DATE', label: 'Disposal date'},
      {path: 'installation_country', valueType: 'TEXT', label: 'Installation country'}
    ],
    references: [
      {referencePath: 'components.primary_component', targetSubjectType: 'component', label: 'Primary component', referenceType: 'HARD'},
      {referencePath: 'components.junction_box', targetSubjectType: 'junction_box', label: 'Junction box', referenceType: 'HARD'},
      {referencePath: 'components.connector', targetSubjectType: 'connector', label: 'Connector', referenceType: 'HARD'},
      {referencePath: 'components.cable', targetSubjectType: 'cable', label: 'Cable', referenceType: 'HARD'}
    ]
  },
  inverter: {
    parameters: [
      ...GENERIC_FALLBACK_PARAMETERS,
      {path: 'rated_power_kw', valueType: 'NUMBER', label: 'Rated power (kW)'},
      {path: 'max_ac_power_watts', valueType: 'NUMBER', label: 'Max AC power (W)'},
      {path: 'certification_status', valueType: 'ENUM', label: 'Certification status', enumValues: ['certified', 'pending', 'expired']},
      {path: 'repairable', valueType: 'BOOLEAN', label: 'Repairable'},
      {path: 'failure_count', valueType: 'NUMBER', label: 'Failure count'},
      {path: 'firmware_version', valueType: 'TEXT', label: 'Firmware version'}
    ]
  },
  battery_pack: {
    parameters: [
      ...GENERIC_FALLBACK_PARAMETERS,
      {path: 'capacity_kwh', valueType: 'NUMBER', label: 'Capacity (kWh)'},
      {path: 'chemistry', valueType: 'ENUM', label: 'Chemistry', enumValues: ['LFP', 'NMC', 'NCA']},
      {path: 'lithium_mass_kg', valueType: 'NUMBER', label: 'Lithium mass (kg)'},
      {path: 'cobalt_mass_kg', valueType: 'NUMBER', label: 'Cobalt mass (kg)'},
      {path: 'recycling_required', valueType: 'BOOLEAN', label: 'Recycling required'}
    ],
    references: [
      {referencePath: 'cell_component', targetSubjectType: 'component', label: 'Cell component', referenceType: 'SOFT'}
    ]
  },
  pv_installation: {
    parameters: [
      ...GENERIC_FALLBACK_PARAMETERS,
      {path: 'installation_id', valueType: 'TEXT', label: 'Installation id'},
      {path: 'location_country', valueType: 'TEXT', label: 'Location country'},
      {path: 'commissioning_year', valueType: 'NUMBER', label: 'Commissioning year'},
      {path: 'total_power_kw', valueType: 'NUMBER', label: 'Total power (kW)'},
      {path: 'module_count', valueType: 'NUMBER', label: 'Module count'},
      {path: 'grid_connected', valueType: 'BOOLEAN', label: 'Grid connected'},
      {path: 'inspection_status', valueType: 'ENUM', label: 'Inspection status', enumValues: ['passed', 'pending', 'overdue', 'failed']},
      {path: 'has_fire_incident', valueType: 'BOOLEAN', label: 'Has fire incident'}
    ],
    references: [
      {referencePath: 'primary_module', targetSubjectType: 'pv_module', label: 'Primary module', referenceType: 'HARD'},
      {referencePath: 'inverter', targetSubjectType: 'inverter', label: 'Inverter', referenceType: 'HARD'}
    ]
  },
  recycling_batch: {
    parameters: [
      ...GENERIC_FALLBACK_PARAMETERS,
      {path: 'disposal_method', valueType: 'ENUM', label: 'Disposal method', enumValues: ['mechanical_recycling', 'thermal_recovery', 'controlled_landfill']},
      {path: 'disposal_year', valueType: 'NUMBER', label: 'Disposal year'},
      {path: 'recovered_glass_kg', valueType: 'NUMBER', label: 'Recovered glass (kg)'},
      {path: 'recovered_aluminium_kg', valueType: 'NUMBER', label: 'Recovered aluminium (kg)'},
      {path: 'landfill_fraction_pct', valueType: 'NUMBER', label: 'Landfill fraction (%)'},
      {path: 'toxic_leak_reported', valueType: 'BOOLEAN', label: 'Toxic leak reported'}
    ],
    references: [
      {referencePath: 'disposed_module', targetSubjectType: 'pv_module', label: 'Disposed module', referenceType: 'HARD'}
    ]
  },
  disposal_record: {
    parameters: [
      ...GENERIC_FALLBACK_PARAMETERS,
      {path: 'disposal_method', valueType: 'ENUM', label: 'Disposal method', enumValues: ['mechanical_recycling', 'thermal_recovery', 'controlled_landfill']},
      {path: 'recovered_aluminium_kg', valueType: 'NUMBER', label: 'Recovered aluminium (kg)'},
      {path: 'toxic_leak_reported', valueType: 'BOOLEAN', label: 'Toxic leak reported'}
    ],
    references: [
      {referencePath: 'disposed_module', targetSubjectType: 'pv_module', label: 'Disposed module', referenceType: 'HARD'}
    ]
  },
  component: {
    parameters: [
      ...GENERIC_FALLBACK_PARAMETERS,
      {path: 'component_category', valueType: 'TEXT', label: 'Component category'},
      {path: 'recycled_content_pct', valueType: 'NUMBER', label: 'Recycled content (%)'},
      {path: 'hazardous_substance_flag', valueType: 'BOOLEAN', label: 'Hazardous substance'}
    ]
  }
};
