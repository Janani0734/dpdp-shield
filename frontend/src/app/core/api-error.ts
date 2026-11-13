import { HttpErrorResponse } from '@angular/common/http';

export type ApiErrorKind =
  | 'network'
  | 'validation'
  | 'not-found'
  | 'forbidden'
  | 'rate-limit'
  | 'unavailable'
  | 'server'
  | 'unknown';

export interface ApiError {
  status: number;
  kind: ApiErrorKind;
  message: string;
}

interface FastApiValidationItem {
  loc?: unknown[];
  msg?: string;
}

/** FastAPI sends `detail` as a string for our own errors and as an array for request-body validation. */
export function detailToMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return (detail as FastApiValidationItem[])
      .map((d) => {
        const field = (d.loc ?? []).filter((x) => x !== 'body').join('.');
        return field ? `${field}: ${d.msg ?? 'invalid'}` : (d.msg ?? 'invalid');
      })
      .join('; ');
  }
  return '';
}

export function toApiError(err: unknown): ApiError {
  if (!(err instanceof HttpErrorResponse)) {
    return { status: 0, kind: 'unknown', message: 'Something unexpected went wrong.' };
  }
  const detail = detailToMessage((err.error as { detail?: unknown } | null)?.detail);
  switch (true) {
    case err.status === 0:
      return { status: 0, kind: 'network', message: 'Cannot reach the DPDP-Shield API. Check that the backend is running and the API address is correct.' };
    case err.status === 400 || err.status === 422:
      return { status: err.status, kind: 'validation', message: detail || 'The request was not accepted.' };
    case err.status === 403:
      return { status: 403, kind: 'forbidden', message: detail || 'This action is disabled on this server.' };
    case err.status === 404:
      return { status: 404, kind: 'not-found', message: detail || 'Not found. The policy may have been deleted or the server restarted.' };
    case err.status === 429:
      return { status: 429, kind: 'rate-limit', message: detail || 'Too many requests. Please wait a minute and try again.' };
    case err.status === 503:
      return { status: 503, kind: 'unavailable', message: detail || 'A backend service is temporarily unavailable.' };
    case err.status >= 500:
      return { status: err.status, kind: 'server', message: detail || 'The server reported an error.' };
    default:
      return { status: err.status, kind: 'unknown', message: detail || `Request failed (HTTP ${err.status}).` };
  }
}
