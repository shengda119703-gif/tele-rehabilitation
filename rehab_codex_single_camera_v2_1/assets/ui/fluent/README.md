# Fluent token provenance

Source: <https://github.com/ejacques11/pyside6-fluent-ui>, skill version
`0.7.0-rc.1`, inspected upstream revision
`4538e312ee9abde4b77d041d59a5392aa7d43188`.

Only the resolved Fluent 2 color snapshot, Qt alias map and provenance/notices
are vendored here. `LICENSE` is the skill's MIT license; `NOTICE.md` preserves
the upstream third-party notices, including Microsoft token attribution.
The notice mentions additional upstream assets which are **not** copied here:
no templates, component library, Fluent icons, React code or workbench shell
are shipped with this product. Existing `assets/ui/ankang` SVG icons remain.

`app/ui/product_theme.py` resolves neutral aliases through the pinned official
token names, then applies this product's centralized green/status/spacing/type
aliases. Native Qt controls, QPalette and generated scoped QSS consume these
values. No npm/Python UI library is loaded, and no requirements change is needed.
The PC product keeps its native window frame and fixed seven-page navigation.

Light is the current product default. Dark and explicit supplied-palette
high-contrast modes are component validation paths for the three migrated
regions, not a claim that every retained screen has a finished dark theme or
that OS high-contrast detection has been integrated. Unmigrated pages and the
original rehabilitation workspace keep their existing compatibility style.
