import { HttpErrorResponse } from '@angular/common/http';
import { describe, expect, it } from 'vitest';
import { detailToMessage, toApiError } from './api-error';

const http = (status: number, detail?: unknown) => new HttpErrorResponse({ status, error: detail === undefined ? null : { detail } });

describe('toApiError', () => {
  it('maps a network failure (status 0) to a clear message', () => {
    const e = toApiError(new HttpErrorResponse({ status: 0 }));
    expect(e.kind).toBe('network');
    expect(e.message).toMatch(/Cannot reach/);
  });

  it('keeps the backend string detail for 400/404/403/503', () => {
    expect(toApiError(http(400, 'This file is not a valid PDF.'))).toMatchObject({ kind: 'validation', message: 'This file is not a valid PDF.' });
    expect(toApiError(http(404, 'Unknown policy_id. Upload the policy first.')).kind).toBe('not-found');
    expect(toApiError(http(403, 'Uploads are disabled on this server.')).kind).toBe('forbidden');
    expect(toApiError(http(503, 'Embedding service unavailable')).kind).toBe('unavailable');
  });

  it('maps 429 to rate-limit and other 5xx to server', () => {
    expect(toApiError(http(429)).kind).toBe('rate-limit');
    expect(toApiError(http(500)).kind).toBe('server');
  });

  it('flattens the FastAPI validation array form of `detail`', () => {
    const detail = [{ loc: ['body', 'question'], msg: 'String should have at least 1 character' }];
    expect(detailToMessage(detail)).toBe('question: String should have at least 1 character');
    expect(toApiError(http(422, detail)).message).toContain('question');
  });

  it('never throws on unexpected input', () => {
    expect(toApiError('boom').kind).toBe('unknown');
    expect(toApiError(http(418)).message).toContain('418');
  });
});
