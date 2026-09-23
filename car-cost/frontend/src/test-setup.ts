import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Sans ce nettoyage, un rendu survit au test suivant et le fait passer — ou
// échouer — pour de mauvaises raisons.
afterEach(cleanup);
