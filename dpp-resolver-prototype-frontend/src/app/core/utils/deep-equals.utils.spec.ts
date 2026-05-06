import { describe, it, expect } from 'vitest';
import { deepEqual } from './deep-equals.utils';

describe('DeepEqualsUtils', () => {
  describe('deepEqual', () => {
    describe('Primitives', () => {
      it('should return true for identical primitives', () => {
        expect(deepEqual(1, 1)).toBe(true);
        expect(deepEqual('test', 'test')).toBe(true);
        expect(deepEqual(true, true)).toBe(true);
        expect(deepEqual(null, null)).toBe(true);
        expect(deepEqual(undefined, undefined)).toBe(true);
      });

      it('should return true for NaN comparison', () => {
        expect(deepEqual(NaN, NaN)).toBe(true);
      });

      it('should return false for different primitives', () => {
        expect(deepEqual(1, 2)).toBe(false);
        expect(deepEqual('test', 'other')).toBe(false);
        expect(deepEqual(true, false)).toBe(false);
        expect(deepEqual(null, undefined)).toBe(false);
        expect(deepEqual(0, false)).toBe(false);
        expect(deepEqual('', false)).toBe(false);
      });

      it('should return false for different types', () => {
        expect(deepEqual(1, '1')).toBe(false);
        expect(deepEqual(true, 1)).toBe(false);
        expect(deepEqual({}, [])).toBe(false);
      });
    });

    describe('Arrays', () => {
      it('should return true for identical simple arrays', () => {
        expect(deepEqual([1, 2, 3], [1, 2, 3])).toBe(true);
        expect(deepEqual(['a', 'b'], ['a', 'b'])).toBe(true);
        expect(deepEqual([], [])).toBe(true);
      });

      it('should return false for arrays with different lengths', () => {
        expect(deepEqual([1, 2], [1, 2, 3])).toBe(false);
      });

      it('should return false for arrays with different elements', () => {
        expect(deepEqual([1, 2, 3], [1, 2, 4])).toBe(false);
      });

      it('should return true for nested arrays', () => {
        expect(deepEqual([1, [2, 3]], [1, [2, 3]])).toBe(true);
      });

      it('should return false for different nested arrays', () => {
        expect(deepEqual([1, [2, 3]], [1, [2, 4]])).toBe(false);
      });
    });

    describe('Objects', () => {
      it('should return true for identical simple objects', () => {
        expect(deepEqual({ a: 1, b: 2 }, { a: 1, b: 2 })).toBe(true);
        expect(deepEqual({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(true);
        expect(deepEqual({}, {})).toBe(true);
      });

      it('should return false for objects with different keys', () => {
        expect(deepEqual({ a: 1 }, { b: 1 })).toBe(false);
        expect(deepEqual({ a: 1 }, { a: 1, b: 2 })).toBe(false);
      });

      it('should return false for objects with different values', () => {
        expect(deepEqual({ a: 1 }, { a: 2 })).toBe(false);
      });

      it('should return true for nested objects', () => {
        expect(deepEqual({ a: { b: 1 } }, { a: { b: 1 } })).toBe(true);
      });

      it('should return false for different nested objects', () => {
        expect(deepEqual({ a: { b: 1 } }, { a: { b: 2 } })).toBe(false);
      });
    });

    describe('Complex/Recursive structures', () => {
      it('should return true for deeply nested mixed structures', () => {
        const obj1 = {
          a: 1,
          b: {
            c: [1, 2, { d: 'test' }],
            e: null,
            f: undefined,
            g: [ { h: 1 } ]
          }
        };
        const obj2 = {
          a: 1,
          b: {
            c: [1, 2, { d: 'test' }],
            e: null,
            f: undefined,
            g: [ { h: 1 } ]
          }
        };
        expect(deepEqual(obj1, obj2)).toBe(true);
      });

      it('should return false for deeply nested structures with minor difference', () => {
        const obj1 = {
          a: 1,
          b: {
            c: [1, 2, { d: 'test' }],
            e: null
          }
        };
        const obj2 = {
          a: 1,
          b: {
            c: [1, 2, { d: 'test' }],
            e: 0 // null vs 0
          }
        };
        expect(deepEqual(obj1, obj2)).toBe(false);
      });

      it('should handle arrays of objects', () => {
        const arr1 = [{ a: 1 }, { b: 2 }];
        const arr2 = [{ a: 1 }, { b: 2 }];
        expect(deepEqual(arr1, arr2)).toBe(true);
      });
    });
  });
});
