import { render, screen } from "@testing-library/react";

import { RankerBadge } from "./RankerBadge";

it("shows the NVIDIA badge when NVIDIA ranked the passages", () => {
  render(<RankerBadge ranker="nvidia" />);
  expect(screen.getByText("Ranked by NVIDIA")).toBeInTheDocument();
});

it("warns when NVIDIA failed and local ranking was used", () => {
  render(<RankerBadge ranker="local" note="NVIDIA reranking timed out. Used local ranking." />);
  expect(screen.getByText(/NVIDIA unavailable/)).toHaveAttribute("title", expect.stringContaining("timed out"));
});

it("shows nothing when NVIDIA is simply off", () => {
  const { container } = render(<RankerBadge ranker="local" note="NVIDIA reranking not used: no consent given." />);
  expect(container).toBeEmptyDOMElement();
});
