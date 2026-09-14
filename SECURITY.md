# Security and data handling

Spatial Prep is designed for a single user on a local computer. It is not a hosted multi-user service and does not implement authentication, encryption at rest, audit trails, retention enforcement or institutional compliance certification.

## Data boundaries

- Browser-to-analyzer requests remain on loopback; image processing is in memory.
- Browser IndexedDB retains experiments, source images and analysis results. Backups include these data and may include original metadata.
- Tissue photographs, textual IDs and notes may appear in exported instruction reports. Excluding an identifier-side photo does not make a report de-identified.
- Static HTTP access is restricted to an explicit set of app assets. Local ID lists, photographs, source code and Git metadata are not served.
- A local capture quarantine can be configured in `.local/blocked-capture-hashes.json`. It is excluded from publication and cannot replace checking the physical label.

Use an approved device, capture app, transfer route and storage location when handling identifiable information. Do not publish screenshots, project backups, ID lists or logs containing real data. A file named “dummy” is not evidence that its contents are synthetic.

## Reporting a concern

Do not place patient information or credentials in public issues, discussions or pull requests. Report security issues privately to the repository owner; arrange an approved transfer route before sharing sensitive evidence. Use synthetic reproductions where possible.

## Publication review

The release snapshot uses an explicit file manifest and independent Git history. Automated screening detects selected identifier and credential patterns, unexpected files and media changes; it cannot establish the absence of all PHI. The maintainer must review the final artifacts and repository visibility before publication.
