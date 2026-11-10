import { fireEvent, render, screen } from "@testing-library/react";

import { CitationChip, linkCitations, Markdown } from "./Markdown";

const src = { label: 1, document_id: "d1", document_title: "Cardiac Anatomy", page_number: 4, page_kind: "page",
  section: "Valves", snippet: "The mitral valve…", score: 0.8 };

describe("linkCitations", () => {
  it("expands single, list and range citations", () => {
    expect(linkCitations("a [1] b [2, 3] c [4-6]")).toBe(
      "a [1](#cite-1) b [2](#cite-2)[3](#cite-3) c [4](#cite-4)[5](#cite-5)[6](#cite-6)");
  });
  it("leaves real markdown links alone", () => {
    expect(linkCitations("[1](http://x)")).toBe("[1](http://x)");
  });
});

describe("Markdown citations", () => {
  it("renders known citations as clickable chips with document and page", () => {
    const onCite = vi.fn();
    render(<Markdown content="Blood crosses the mitral valve [1]." sources={[src]} onCite={onCite} />);
    const chip = screen.getByRole("button", { name: "1" });
    expect(chip).toHaveAttribute("title", "Cardiac Anatomy — page 4 · Valves");
    fireEvent.click(chip);
    expect(onCite).toHaveBeenCalledWith(src);
  });
  it("flags citations that do not match a retrieved source", () => {
    render(<CitationChip n={9} />);
    expect(screen.getByText("?9")).toHaveAttribute("title", expect.stringContaining("does not match"));
  });
  it("marks the AI-generated section heading", () => {
    render(<Markdown content={"### Additional explanation (AI-generated)\nText"} />);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("✦");
  });
});
