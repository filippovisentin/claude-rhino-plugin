# Fonts

Used by `docs/overview.html` to render `docs/rhino-plugin-overview.pdf`. All are licensed under the SIL Open Font License 1.1.

- Instrument Sans and Instrument Serif, by the Instrument project authors. License: `InstrumentSans-OFL.txt`
- Geist Mono, by Vercel. License: `GeistMono-OFL.txt`

To rebuild the PDF, print `overview.html` from Chrome with no margins, or run headless:

```bash
chrome --headless=new --no-pdf-header-footer --print-to-pdf=docs/rhino-plugin-overview.pdf docs/overview.html
```
