import { describe, it, expect } from "vitest";
import { parseSSELine, formatPayload } from "../lib";

describe("parseSSELine", () => {
  it("extracts token from a valid data line", () => {
    const line = 'data: {"token": "Hello"}';
    expect(parseSSELine(line)).toBe("Hello");
  });

  it("returns [DONE] sentinel for done marker", () => {
    expect(parseSSELine("data: [DONE]")).toBe("[DONE]");
  });

  it("returns null for non-data lines", () => {
    expect(parseSSELine("")).toBeNull();
    expect(parseSSELine("event: message")).toBeNull();
    expect(parseSSELine(": comment")).toBeNull();
    expect(parseSSELine("id: 123")).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseSSELine("data: {bad json}")).toBeNull();
    expect(parseSSELine("data: not-json")).toBeNull();
  });

  it("returns null when JSON has no token field", () => {
    expect(parseSSELine('data: {"other": "value"}')).toBeNull();
  });

  it("returns null for empty data payload", () => {
    expect(parseSSELine("data: ")).toBeNull();
    expect(parseSSELine("data:")).toBeNull();
  });

  it("handles extra whitespace around the line", () => {
    expect(parseSSELine('  data: {"token": "hi"}  ')).toBe("hi");
  });

  it("handles data: with no space before JSON", () => {
    expect(parseSSELine('data:{"token": "world"}')).toBe("world");
  });
});

describe("formatPayload", () => {
  it("formats with default parameters", () => {
    const result = JSON.parse(formatPayload("What is life?"));
    expect(result).toEqual({
      question: "What is life?",
      max_tokens: 512,
      temperature: 0.7,
    });
  });

  it("formats with custom parameters", () => {
    const result = JSON.parse(formatPayload("Hello", 256, 0.9));
    expect(result).toEqual({
      question: "Hello",
      max_tokens: 256,
      temperature: 0.9,
    });
  });

  it("returns valid JSON string", () => {
    const payload = formatPayload("test");
    expect(() => JSON.parse(payload)).not.toThrow();
  });
});
