import { Injectable, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ApiError, toApiError } from './api-error';
import { ApiService } from './api.service';
import { QueryResult } from './models';

export interface ChatTurn {
  id: number;
  policyId: string;
  question: string;
  result: QueryResult;
}

/** Question history for this browser session. One request at a time; never retried automatically. */
@Injectable({ providedIn: 'root' })
export class ChatStore {
  private readonly api = inject(ApiService);
  private sub: Subscription | null = null;
  private seq = 0;

  readonly turns = signal<ChatTurn[]>([]);
  readonly pendingQuestion = signal<string | null>(null);
  readonly error = signal<ApiError | null>(null);

  ask(policyId: string, question: string): void {
    if (this.pendingQuestion()) return;
    this.pendingQuestion.set(question);
    this.error.set(null);
    this.sub = this.api.query(policyId, question).subscribe({
      next: (result) => {
        this.turns.update((t) => [...t, { id: ++this.seq, policyId, question, result }]);
        this.pendingQuestion.set(null);
      },
      error: (e: unknown) => {
        this.error.set(toApiError(e));
        this.pendingQuestion.set(null);
      },
    });
  }

  /** Stops waiting for the answer; the server may still complete (and log) the request. */
  cancel(): void {
    this.sub?.unsubscribe();
    this.sub = null;
    this.pendingQuestion.set(null);
  }

  forgetPolicy(policyId: string): void {
    this.turns.update((t) => t.filter((x) => x.policyId !== policyId));
  }
}
