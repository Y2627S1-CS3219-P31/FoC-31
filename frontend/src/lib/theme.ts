// AI-assisted (OpenCode + Claude): Mantine theme tokens derived from the
// team's Penpot wireframe (colors, radius, primary button). Reviewed by authors.
import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Primary blue sampled from the wireframe's primary buttons (~#4A6FA5).
const brand: MantineColorsTuple = [
  "#eef2f9",
  "#dbe2ef",
  "#b4c3dd",
  "#8aa2cb",
  "#6886bc",
  "#5474b3",
  "#4a6fa5", // index 6 = primary shade
  "#3d5d8f",
  "#345080",
  "#284470",
];

export const theme = createTheme({
  primaryColor: "brand",
  primaryShade: 6,
  colors: { brand },
  defaultRadius: "md",
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  headings: {
    fontWeight: "700",
  },
});
