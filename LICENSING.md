# Licensing

Spatial Prep is available under the [PolyForm Noncommercial License 1.0.0](LICENSE). The standard license text is included unchanged.

Permitted noncommercial use is free. The license also permits use by educational institutions, public research organizations and the other organizations it lists regardless of funding source. This includes sponsored research within those permissions. The full license controls the scope; it is broader than an academic-only license.

Uses outside those permissions require a separate written agreement with the rights holder. See [Commercial licensing](COMMERCIAL_LICENSE.md). The public license grants no additional commercial rights, and this repository sets no commercial price.

This is source-available software, not [OSI open source](https://opensource.org/osd). Software licensing does not establish laboratory validation, clinical approval or authorization to process identifiable data.

Before making this release public, the maintainer must confirm institutional ownership and authority to offer both licensing routes. Review rights to outside contributions before accepting them; a noncommercial contribution alone may not grant commercial relicensing rights.

## Dependencies

Python dependencies retain their own licenses. The running app uses OpenCV, NumPy, Pillow, qrcode and ReportLab. PDF development tools use pypdf and pypdfium2/PDFium. Their packages include applicable third-party notices; do not assume the project’s eventual license replaces them.

PyMuPDF has been removed from both runtime and development requirements. Its AGPL/commercial licensing is documented by [Artifex](https://pymupdf.readthedocs.io/en/latest/faq/index.html). The replacements document their terms at [pypdf](https://github.com/py-pdf/pypdf/blob/main/LICENSE) and [pypdfium2](https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing).

Before distributing packaged binaries or dependencies, review the licenses and notices of the exact resolved versions as well as the project license.
