import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import * as renderer from "react-test-renderer";

import CategoryList from "../../category/components/CategoryList";
import categoryListFixture from "./fixtures/categoryList";
import categoryFixture from "./fixtures/category";

describe("<CategoryList />", () => {
  it("renders while data is loading", () => {
    const component = renderer.create(
      <MemoryRouter>
        <CategoryList />
      </MemoryRouter>
    );
    expect(component).toMatchSnapshot();
  });
  it("renders when data is fully loaded", () => {
    const component = renderer.create(
      <MemoryRouter>
        <CategoryList categories={categoryListFixture} />
      </MemoryRouter>
    );
    expect(component).toMatchSnapshot();
  });
  it("renders when category list is empty", () => {
    const component = renderer.create(
      <MemoryRouter>
        <CategoryList categories={[]} />
      </MemoryRouter>
    );
    expect(component).toMatchSnapshot();
  });
});
