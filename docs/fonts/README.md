# Fonts

Used by `docs/overview.html` to render `docs/rhino-plugin-overview.pdf`. All are licensed under the SIL Open Font License 1.1; each license file sits next to its font.

- Bricolage Grotesque (headings). License: `BricolageGrotesque-OFL.txt`
- Work Sans (body text). License: `WorkSans-OFL.txt`
- IBM Plex Mono (labels and code). License: `IBMPlexMono-OFL.txt`

To rebuild the PDF, print `overview.html` from Chrome with no margins, or run headless:

```bash
chrome --headless=new --no-pdf-header-footer --allow-file-access-from-files --print-to-pdf=docs/rhino-plugin-overview.pdf docs/overview.html
```
