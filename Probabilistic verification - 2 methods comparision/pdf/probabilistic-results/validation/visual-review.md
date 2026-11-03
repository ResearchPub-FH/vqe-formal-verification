# Final visual review

Single-column revision, 2026-11-02. The final vector PDF was rendered with Poppler at 100 dpi (`pdf-print-size-100dpi.png`), 150 dpi (`pdf-inspection-150dpi.png`), 300 dpi and 600 dpi. The tight regions were inspected in 600 dpi crops: the (a)/(c) titles and the (c) category labels.

- The 2 x 2 layout places (a) over (b) on the left and (c) over (d) on the right. The shared legend above the panels is legible at the 3.5-inch column width.
- Endpoint markers are complete, including the Storm diamond at K=50.
- Axis labels, grouped-outcome labels, numerical annotations and both resource intervals have no visible overlap or clipping. The three-line no-success label clears "41-50", and the count labels sit above the taller bar of each pair.
- An automated check confirms that every extracted PDF word lies within the page.
- All four resource-mean labels match the full-precision source statistics after formatting.
- PDF size is exactly 252 x 275.04 points (3.5 x 3.82 inches).
- PDF fonts are embedded; PDF/SVG contain no raster image objects. SVG retains editable text.
- The PNG is 2100 x 2292 pixels at 600 dpi.
- Grayscale distinctions are provided by solid/dashed curves, hollow Storm diamonds, hatched/unfilled versus filled outcome bars, and square/circle resource markers. The final PDF was also rendered and inspected in grayscale at 110 dpi.
- The minimum font size is 7 pt (panel titles 7.5 pt).
- All four derived data files are byte-identical to the double-column version. All 421 referenced source files retain their hashes during the build; the supplied paper PDF is now read from `~/Downloads`.

The earlier double-column version's review is preserved in `annotation-checklist.json` and `annotated-reference.pdf`. The source-data, bootstrap, p-value and probability-partition checks are recorded separately in checks.json.
