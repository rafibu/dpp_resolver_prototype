import Ajv2020, {AnySchema, ErrorObject} from 'ajv/dist/2020';
import addFormats from 'ajv-formats';

export type JsonValidationIssue = Pick<ErrorObject, 'instancePath' | 'message' | 'params'>;

export function createJsonSchemaValidator(): Ajv2020 {
  const ajv = new Ajv2020({
    allErrors: true,
    strict: false
  });
  addFormats(ajv);
  return ajv;
}

export function validateJsonPayload(ajv: Ajv2020, schema: unknown, payload: unknown): JsonValidationIssue[] {
  const validate = ajv.compile(schema as AnySchema);
  const valid = validate(payload);
  return valid ? [] : (validate.errors || []).map(error => ({
    instancePath: error.instancePath,
    message: error.message,
    params: error.params
  }));
}
