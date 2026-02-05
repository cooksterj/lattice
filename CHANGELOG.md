# Changelog

## [0.6.0](https://github.com/cooksterj/lattice/compare/v0.5.0...v0.6.0) (2026-02-05)


### Features

* Added additional web functionality. ([5f864a0](https://github.com/cooksterj/lattice/commit/5f864a075a6faf2e986bfe678b3cab2b57f7da44))
* Added and bolstered test conditions. ([cbbcb19](https://github.com/cooksterj/lattice/commit/cbbcb1916e03c4aa8d74b722e8ec884909a9ffa7))
* Assets now support result checking - if configured. ([bcb320f](https://github.com/cooksterj/lattice/commit/bcb320f69070c32e79e6011569e1ba4d6af2c2c0))
* Establish SQLite databases, one for primary execution, and one for the web demo. ([39b7909](https://github.com/cooksterj/lattice/commit/39b7909b66e15f19473b975dc775ac7509c0e977))
* Implementation of phase 6. ([ed79562](https://github.com/cooksterj/lattice/commit/ed7956241a766e57c8d34bec472ddc106799e000))
* Track asset execution lineage, logging, and establish a SQLite database for tracking purposes. ([a5f9bca](https://github.com/cooksterj/lattice/commit/a5f9bcaa37a658520720634db83b0fcae89c6519))
* Updates the web demo to include checks. ([67c8f39](https://github.com/cooksterj/lattice/commit/67c8f39584f2e386cf924695acc9cc7a9e28dc17))
* Visualize previous run in the web UI. ([7560a9a](https://github.com/cooksterj/lattice/commit/7560a9a6bfe04c4a8d51be8b43c217a094c0ea1a))

## [0.5.0](https://github.com/cooksterj/lattice/compare/v0.4.0...v0.5.0) (2026-01-31)


### Features

* A comphrensive logging framework has been added to the project. ([0388a53](https://github.com/cooksterj/lattice/commit/0388a5318d6c891aa5f789374f87033939503666))
* Add the ability to run assets concurrently based on the level of the asset and its dependencies. ([d8a7343](https://github.com/cooksterj/lattice/commit/d8a734390dc52117b3d1ff30c1ea8d12871fd12d))
* Added logging capabilities across all Lattice frameworks. ([084854f](https://github.com/cooksterj/lattice/commit/084854f8b21eb45c3dfa631de6684720deeb888c))
* Configure logging to be present in the web demonstration. ([3c9e942](https://github.com/cooksterj/lattice/commit/3c9e9429a441d294aaab3553b71711b0fc7bbae8))


### Documentation

* Instructions on how to configure logging when using Lattice has been provided. ([d2bb5b7](https://github.com/cooksterj/lattice/commit/d2bb5b72dec8fbdd986c6474be0a513f37ed7a11))
* Updates to the project's README.md to include the benefit of using Lattice. ([e69138d](https://github.com/cooksterj/lattice/commit/e69138d760dfff6fc5a51400f056eeff4b42c67a))

## [0.4.0](https://github.com/cooksterj/lattice/compare/v0.3.0...v0.4.0) (2026-01-31)


### Features

* Added python assets to support phase 3, namely: input/outut managers and an executor. ([fa60d64](https://github.com/cooksterj/lattice/commit/fa60d6490064c6b02370749bc72a21e41a5a2626))
* Added UI improvements. ([d1301f9](https://github.com/cooksterj/lattice/commit/d1301f99c5086a62c0bd72db79a06f299339fedd))
* Added web assets to support phase 2, namely: graph data, asset detail, execution plan, and memory health checks. ([abb3481](https://github.com/cooksterj/lattice/commit/abb34817895081c49f5eb98b49751348de6ba538))
* Bolstered project plan and .gitignore. ([80ac4a6](https://github.com/cooksterj/lattice/commit/80ac4a6168c3304b599f885a97fc301153695b23))
* Pytest support - test driven development. ([0c22ad6](https://github.com/cooksterj/lattice/commit/0c22ad6776f93ca17cbbc7dbaa9f04578db1cf81))
* Updates to the project plan and uv dependencies. ([8e5c64c](https://github.com/cooksterj/lattice/commit/8e5c64c5cc880fe2064e60984408356115206c45))


### Bug Fixes

* Fix an issue that didn't allow asset groups to be properly parsed. ([aa80481](https://github.com/cooksterj/lattice/commit/aa8048135a4f0d273c0a2edfa37ffd2fda0c61bf))

## [0.3.0](https://github.com/cooksterj/lattice/compare/v0.2.0...v0.3.0) (2026-01-30)


### Features

* Added dependency graph resolver, cyclic resolver, and execution plan. ([7f2830f](https://github.com/cooksterj/lattice/commit/7f2830f55d516b29438a029d98f6f295c30ff569))
* Added pre-commit hooks an merge back to the GitHub actions. ([af45b02](https://github.com/cooksterj/lattice/commit/af45b02c79f6c38dc07a7daec453b2cd61229bc0))
* Allow the github actions to actually work. ([ee9f6ec](https://github.com/cooksterj/lattice/commit/ee9f6ecbb1f0b5eb198e1956745f5504156266ec))
* Bolstered doctrings. ([d7171ac](https://github.com/cooksterj/lattice/commit/d7171acc7ec63c00c76f50b11fbbe94b8f0e3977))
* Web service implementation with demo. ([4781b6b](https://github.com/cooksterj/lattice/commit/4781b6bf743e3061258d6cfa1d437bf7a506f60c))

## [0.2.0](https://github.com/cooksterj/lattice/compare/v0.1.0...v0.2.0) (2026-01-30)


### Features

* Phase 1 with additional documentation on phase 2 implementation. ([995b639](https://github.com/cooksterj/lattice/commit/995b63909171fa7081039f724168478c5975402a))


### Documentation

* Updates to README.md. ([a8f9455](https://github.com/cooksterj/lattice/commit/a8f9455223f3944766e99aad3e23d2ed0ea29f57))

## 0.1.0 (2026-01-28)


### Bug Fixes

* remove deprecated package-name from release-please config. ([01b4464](https://github.com/cooksterj/lattice/commit/01b446430e65b1a83bb41a5a01124bc61695184d))
