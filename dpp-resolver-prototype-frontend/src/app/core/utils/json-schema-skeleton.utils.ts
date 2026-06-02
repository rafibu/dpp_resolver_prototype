export function createEmptyPayloadFromSchema(schema: unknown): unknown {
  return emptyValue(schema);
}

function emptyValue(schema: unknown): unknown {
  if (!schema || typeof schema !== 'object') {
    return null;
  }

  const document = schema as Record<string, any>;
  if ('default' in document) {
    return clone(document['default']);
  }
  if ('const' in document) {
    return clone(document['const']);
  }
  if (Array.isArray(document['enum']) && document['enum'].length > 0) {
    return clone(document['enum'][0]);
  }
  if (Array.isArray(document['oneOf']) && document['oneOf'].length > 0) {
    return emptyValue(document['oneOf'][0]);
  }
  if (Array.isArray(document['anyOf']) && document['anyOf'].length > 0) {
    return emptyValue(document['anyOf'][0]);
  }

  const type = Array.isArray(document['type'])
    ? document['type'].find((entry: string) => entry !== 'null') ?? document['type'][0]
    : document['type'];

  if (type === 'object' || document['properties']) {
    return Object.entries(document['properties'] ?? {}).reduce<Record<string, unknown>>((result, [key, value]) => {
      result[key] = emptyValue(value);
      return result;
    }, {});
  }
  if (type === 'array') {
    return [];
  }
  if (type === 'integer' || type === 'number') {
    return 0;
  }
  if (type === 'boolean') {
    return false;
  }
  if (type === 'string') {
    return '';
  }

  return null;
}

function clone<T>(value: T): T {
  return typeof structuredClone === 'function'
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}
