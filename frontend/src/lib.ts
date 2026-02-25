/**
 * Parse a single SSE line and extract the token text, if any.
 * Returns the token string, null if not a data line, or "[DONE]" sentinel.
 */
export function parseSSELine(line: string): string | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("data:")) return null;

  const data = trimmed.slice(5).trim();
  if (data === "[DONE]") return "[DONE]";

  try {
    const parsed = JSON.parse(data);
    return parsed.token ?? null;
  } catch {
    return null;
  }
}

/**
 * Build the JSON payload for the /api/ask endpoint.
 */
export function formatPayload(question: string, maxTokens = 512, temperature = 0.7): string {
  return JSON.stringify({ question, max_tokens: maxTokens, temperature });
}
