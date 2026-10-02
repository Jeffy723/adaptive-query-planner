/**
 * frontend/src/api/client.ts
 *
 * REST API client functions for executing queries and fetching backend examples.
 */

import type { ExampleQuery, PipelineResponse } from '../types/pipeline';

const BASE_URL = ''; // Relative URL handled by Vite proxy in dev, direct in prod

export async function fetchHealth(): Promise<{ status: string; dataset_rows: number }> {
  const resp = await fetch(`${BASE_URL}/api/health`);
  if (!resp.ok) {
    throw new Error(`Health check failed: ${resp.statusText}`);
  }
  return resp.json();
}

export async function fetchExamples(): Promise<ExampleQuery[]> {
  const resp = await fetch(`${BASE_URL}/api/examples`);
  if (!resp.ok) {
    throw new Error(`Failed to load examples: ${resp.statusText}`);
  }
  const data = await resp.json();
  return data.examples || [];
}

export async function executeQuery(
  query: string,
  enableLearning: boolean = false,
  alpha: number = 0.5,
  resetLearnedStats: boolean = false
): Promise<PipelineResponse> {
  const resp = await fetch(`${BASE_URL}/api/query/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      enable_learning: enableLearning,
      alpha,
      reset_learned_stats: resetLearnedStats,
    }),
  });

  if (!resp.ok && resp.status >= 500) {
    const errorData = await resp.json().catch(() => null);
    throw new Error(errorData?.error?.message || `Server error: ${resp.statusText}`);
  }

  return resp.json();
}

export async function resetAdaptiveStats(): Promise<{ status: string; message: string }> {
  const resp = await fetch(`${BASE_URL}/api/adaptive/reset`, {
    method: 'POST',
  });
  if (!resp.ok) {
    throw new Error(`Failed to reset adaptive stats: ${resp.statusText}`);
  }
  return resp.json();
}
