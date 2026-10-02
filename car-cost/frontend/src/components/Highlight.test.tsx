import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Highlight } from "./Highlight";

describe("Highlight", () => {
  it("un libellé hostile s'affiche en texte", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const { container } = render(<Highlight text={hostile} query="img" />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe(hostile);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("img");
  });

  it("électrique et electrique surlignent pareil", () => {
    for (const query of ["electrique", "électrique"]) {
      const { container, unmount } = render(
        <Highlight text="Faisceau électrique" query={query} />,
      );
      expect(container.querySelector("mark")?.textContent).toBe("électrique");
      unmount();
    }
  });
});
