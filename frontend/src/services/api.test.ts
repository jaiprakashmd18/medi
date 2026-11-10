import { parseSSE } from "./api";
import { speakableText } from "@/hooks/useSpeech";

describe("parseSSE", () => {
  it("parses event and JSON data", () => {
    expect(parseSSE('event: delta\ndata: {"text":"hi"}')).toEqual({ event: "delta", data: { text: "hi" } });
  });
  it("returns null without data or with bad JSON", () => {
    expect(parseSSE("event: ping")).toBeNull();
    expect(parseSSE("data: {oops")).toBeNull();
  });
});

describe("speakableText", () => {
  it("strips markdown and citation markers for speech", () => {
    expect(speakableText("## Heart\n**Mitral** valve [1][2] (AI explanation)")).toBe("Heart Mitral valve");
  });
});
