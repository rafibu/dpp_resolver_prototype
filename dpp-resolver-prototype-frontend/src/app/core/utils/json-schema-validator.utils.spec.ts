import {describe, expect, it} from 'vitest';
import {createJsonSchemaValidator, validateJsonPayload} from './json-schema-validator.utils';

describe('JsonSchemaValidatorUtils', () => {
  it('should validate draft 2020-12 schemas with DPP extension keywords', () => {
    const ajv = createJsonSchemaValidator();
    const schema = {
      '$schema': 'https://json-schema.org/draft/2020-12/schema',
      '$id': 'https://schemas.dpp.eu/pv_module/1.0',
      type: 'object',
      properties: {
        serial_number: {type: 'string'},
        component: {
          type: 'object',
          'x-dpp-reference': 'inverter',
          properties: {
            '$ref': {type: 'string'}
          }
        }
      },
      required: ['serial_number']
    };

    expect(validateJsonPayload(ajv, schema, {serial_number: 'PV-1'})).toEqual([]);
    expect(validateJsonPayload(ajv, schema, {})).toEqual([
      expect.objectContaining({instancePath: '', message: expect.stringContaining('required')})
    ]);
  });
});
