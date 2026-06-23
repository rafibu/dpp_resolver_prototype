import {describe, expect, it} from 'vitest';
import {QueryMetadataService} from './query-metadata.service';
import {PredicateOperator} from './models/query.model';

describe('QueryMetadataService', () => {
  const service = new QueryMetadataService();

  describe('operatorsForValueType', () => {
    it('restricts BOOLEAN to equality/existence operators', () => {
      expect(service.operatorsForValueType('BOOLEAN')).toEqual([
        PredicateOperator.EQ, PredicateOperator.NEQ, PredicateOperator.EXISTS, PredicateOperator.NOT_EXISTS
      ]);
    });

    it('includes comparison operators for NUMBER', () => {
      const operators = service.operatorsForValueType('NUMBER');
      expect(operators).toContain(PredicateOperator.GT);
      expect(operators).toContain(PredicateOperator.LTE);
      expect(operators).toContain(PredicateOperator.IN);
    });

    it('keeps DATE to equality/existence/list operators until platforms support temporal comparison', () => {
      const operators = service.operatorsForValueType('DATE');
      expect(operators).toContain(PredicateOperator.IN);
      expect(operators).not.toContain(PredicateOperator.GT);
    });

    it('uses equality + IN for ENUM and TEXT', () => {
      expect(service.operatorsForValueType('ENUM')).toContain(PredicateOperator.IN);
      expect(service.operatorsForValueType('TEXT')).not.toContain(PredicateOperator.GT);
    });
  });

  describe('fallbackMetadata', () => {
    it('returns S4-compatible parameters flagged as fallback', () => {
      const metadata = service.fallbackMetadata('pv_module');
      expect(metadata.isFallback).toBe(true);
      const paths = metadata.predicateParameters.map(parameter => parameter.path);
      expect(paths).toContain('contains_lead');
      expect(paths).toContain('nominal_power_w');
      const referencePaths = metadata.referencePaths.map(reference => reference.referencePath);
      expect(referencePaths).toContain('components.primary_component');
    });
  });

  describe('deriveFromSchema', () => {
    it('maps JSON schema properties into typed, selectable parameters', () => {
      const schema = {
        type: 'object',
        required: ['serial_number'],
        properties: {
          serial_number: {type: 'string'},
          nominal_power_w: {type: 'number'},
          contains_lead: {type: 'boolean'},
          chemistry: {type: 'string', enum: ['LFP', 'NMC']},
          commissioned_at: {type: 'string', format: 'date'},
          manufacturer: {
            type: 'object',
            properties: {country: {type: 'string'}}
          },
          inverter: {
            type: 'object',
            'x-dpp-reference': 'inverter',
            properties: {$ref: {type: 'string'}}
          }
        }
      };

      const metadata = service.deriveFromSchema('pv_module', schema);
      const byPath = new Map(metadata.predicateParameters.map(parameter => [parameter.path, parameter]));

      expect(byPath.get('serial_number')?.valueType).toBe('TEXT');
      expect(byPath.get('serial_number')?.required).toBe(true);
      expect(byPath.get('nominal_power_w')?.valueType).toBe('NUMBER');
      expect(byPath.get('contains_lead')?.valueType).toBe('BOOLEAN');
      expect(byPath.get('chemistry')?.valueType).toBe('ENUM');
      expect(byPath.get('chemistry')?.enumValues).toEqual(['LFP', 'NMC']);
      expect(byPath.get('commissioned_at')?.valueType).toBe('DATE');
      // Nested objects are flattened into dot paths.
      expect(byPath.get('manufacturer.country')?.valueType).toBe('TEXT');
      // Reference-shaped objects become reference paths.
      expect(metadata.referencePaths.map(reference => reference.referencePath)).toContain('inverter');
      expect(metadata.referencePaths[0].targetSubjectType).toBe('inverter');
    });

    it('preserves numeric and boolean enum scalars from a schema', () => {
      const metadata = service.deriveFromSchema('custom', {
        type: 'object',
        properties: {
          rank: {type: 'integer', enum: [0, 1]},
          enabled: {type: 'boolean', enum: [true, false]}
        }
      });
      const byPath = new Map(metadata.predicateParameters.map(parameter => [parameter.path, parameter]));
      expect(byPath.get('rank')?.enumValues).toEqual([0, 1]);
      expect(byPath.get('enabled')?.enumValues).toEqual([true, false]);
    });
  });

  describe('getMetadata', () => {
    it('prefers schema-derived metadata when usable', () => {
      const metadata = service.getMetadata('pv_module', {
        type: 'object',
        properties: {nominal_power_w: {type: 'number'}}
      });
      expect(metadata.isFallback).toBeFalsy();
      expect(metadata.predicateParameters[0].path).toBe('nominal_power_w');
    });

    it('falls back to local metadata for a permissive schema', () => {
      const metadata = service.getMetadata('pv_module', {type: 'object', additionalProperties: true});
      expect(metadata.isFallback).toBe(true);
    });
  });
});
