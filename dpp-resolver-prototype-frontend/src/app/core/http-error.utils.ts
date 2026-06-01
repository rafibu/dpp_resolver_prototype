import {HttpErrorResponse} from '@angular/common/http';

export function toErrorMessage(error: unknown, fallback = 'Request failed'): string {
  if (error instanceof HttpErrorResponse) {
    const payloadMessage = readPayloadMessage(error.error);
    if (payloadMessage) {
      return payloadMessage;
    }

    if (error.status === 0) {
      return `${fallback}: service is unreachable`;
    }

    const statusText = error.statusText || 'HTTP error';
    return `${fallback}: ${error.status} ${statusText}`;
  }

  if (error instanceof Error && error.message) {
    return `${fallback}: ${error.message}`;
  }

  return fallback;
}

function readPayloadMessage(payload: unknown): string | null {
  if (typeof payload === 'string' && payload.trim()) {
    return payload;
  }

  if (!payload || typeof payload !== 'object') {
    return null;
  }

  const body = payload as Record<string, unknown>;
  for (const key of ['detail', 'message', 'error']) {
    const value = body[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }

  return null;
}
