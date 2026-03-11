# Changelog

## [0.10.2](https://github.com/cooksterj/lattice/compare/v0.10.1...v0.10.2) (2026-03-11)


### Documentation

* add web visualization demo gif ([01730a2](https://github.com/cooksterj/lattice/commit/01730a288d12a142ad44d6d76c19e905f64f0c04))

## [0.10.1](https://github.com/cooksterj/lattice/compare/v0.10.0...v0.10.1) (2026-02-22)


### Bug Fixes

* **release:** use env vars for uv publish CodeArtifact auth ([67b1ab9](https://github.com/cooksterj/lattice/commit/67b1ab9bf2da79b73de131b5443c2378ac4fcba8))

## [0.10.0](https://github.com/cooksterj/lattice/compare/v0.9.1...v0.10.0) (2026-02-21)


### Features

* add docker-compose.yml for one-command local development ([1432b24](https://github.com/cooksterj/lattice/commit/1432b240f19da76795b1ed70a9096e7fc3f498b4))
* add Dockerfile and .dockerignore for container deployment ([310a97b](https://github.com/cooksterj/lattice/commit/310a97b36ad4d8bb392ac1979401dfd7f574f21a))
* add environment variable configuration for container deployment ([2b2b96f](https://github.com/cooksterj/lattice/commit/2b2b96fd22ad7a6c31f2c9af12bc568a3fb046b3))
* add GitHub Actions workflow to publish to AWS CodeArtifact ([2af5bc8](https://github.com/cooksterj/lattice/commit/2af5bc8caf2ae73d6148f6484409384b7e866c6d))


### Bug Fixes

* copy README.md into Docker build context for hatchling ([f2f3025](https://github.com/cooksterj/lattice/commit/f2f3025e26befe4a0e215dd07425a7170a759920))


### Documentation

* add deployment guide for Docker, ECS Fargate, and EC2 ([8441c0b](https://github.com/cooksterj/lattice/commit/8441c0b97f6c35ceeee9c07a39260f79a54a3dd9))
* add library usage and Docker deployment guide to deployment.md ([3881507](https://github.com/cooksterj/lattice/commit/3881507d566ca7f5bfd485dee11fa69cca820160))

## [0.9.1](https://github.com/cooksterj/lattice/compare/v0.9.0...v0.9.1) (2026-02-21)


### Bug Fixes

* Resolve mypy type errors in dbt manifest and assets modules ([27e0e78](https://github.com/cooksterj/lattice/commit/27e0e786b7a0b4e6f0288c006b9532a80b6e452e))

## [0.9.0](https://github.com/cooksterj/lattice/compare/v0.8.0...v0.9.0) (2026-02-21)


### Features

* Add dbt manifest integration (LAT-2) ([00af09e](https://github.com/cooksterj/lattice/commit/00af09ed0b53205567f449336d57b2e1bc956c1b))
* Add select and deps parameters for tag-based dbt model filtering ([971d75b](https://github.com/cooksterj/lattice/commit/971d75b0948084f2cd208840670a91eff7dd526e))
* Added asset level detail as a browsable web page. ([7ca3bec](https://github.com/cooksterj/lattice/commit/7ca3bec3306c1ac4449c9b970fa8d0cf9a26900d))
* Adjusted the sidebar and header to not overlap while navigating. ([66b1431](https://github.com/cooksterj/lattice/commit/66b14315eb531a51d92b0f56c0fe6a83db62da66))
* Bolster testing coverage output through the existing CI github action. ([aaebfac](https://github.com/cooksterj/lattice/commit/aaebfac23ea59ca592b54417f3ba8194e73690d6))


### Documentation

* Add dbt integration section to core architecture ([d3e2b5e](https://github.com/cooksterj/lattice/commit/d3e2b5ea59bfc95794ed32acc806b74d0c85a9f6))
* Expand _create_stub_fn docstring to explain why stubs exist ([83a813f](https://github.com/cooksterj/lattice/commit/83a813f5f25c4747697074caaab437542a008b4b))

## [0.8.0](https://github.com/cooksterj/lattice/compare/v0.7.0...v0.8.0) (2026-02-20)


### Features

* Core and web architecture markdown documents to describe functionality have been added. ([0d7394b](https://github.com/cooksterj/lattice/commit/0d7394ba661f7ada37d57fea1ca53c892ef07ca7))
* Implementation of phase 7. ([0a2aacf](https://github.com/cooksterj/lattice/commit/0a2aacf31475f85eac52ac6ff75328aae89fa01e))
* Moved all sub-functions up a level and added testing. ([400cd84](https://github.com/cooksterj/lattice/commit/400cd84786c1dd12123b9b3449b94c3a95610da9))
* The asset dependency scheme has been decoupled from the function declaration.  It is now handled directly in the asset decorator. ([353f17b](https://github.com/cooksterj/lattice/commit/353f17be9f58f9ba6375e6544355d26e2ceb437c))
* Updates to the lattice_demo_run database to facilitate the persistance of recent updates. ([36da1de](https://github.com/cooksterj/lattice/commit/36da1de44afa218487ab5182c0546a4754f80988))

## [0.7.0](https://github.com/cooksterj/lattice/compare/v0.6.0...v0.7.0) (2026-02-08)


### Features

* **02-01:** add /asset/{key}/live route with correct ordering and tests ([3bf4bf2](https://github.com/cooksterj/lattice/commit/3bf4bf2ad229415740133a73f03ed103539eb64a))
* **02-01:** create asset_live.html template with asset details panel ([e25f9c2](https://github.com/cooksterj/lattice/commit/e25f9c2fbf5249d4c914989499908307466f7fa2))
* **02-02:** add log entry CSS styles and connection status indicator ([1833e29](https://github.com/cooksterj/lattice/commit/1833e2931c267a620ddd798caa4b79461212cd7f))
* **02-02:** implement WebSocket client with state machine and log rendering ([2b95f39](https://github.com/cooksterj/lattice/commit/2b95f39ad3a755e665e6b9d07d66715067b1c49a))
* **02-03:** add refocus main window button and run history link ([7d09108](https://github.com/cooksterj/lattice/commit/7d0910884be8891f246444fd451f162bc7e3eacb))
* **02-03:** implement completion banner with success/failure styling and duration ([7069eee](https://github.com/cooksterj/lattice/commit/7069eee0443f0c5149dac4dfcbe816765a30481f))
* **03-01:** implement window.open click handler with tracking and popup fallback ([38f5c24](https://github.com/cooksterj/lattice/commit/38f5c24dfff21d4d2388ecb5aff3207f3add4e49))
* **04-01:** add current_page to all route handlers ([edc98b5](https://github.com/cooksterj/lattice/commit/edc98b576a3a555b22fd8056cc57e62d2bcebffd))
* **04-01:** add sidebar CSS to styles.css ([ab0e836](https://github.com/cooksterj/lattice/commit/ab0e836746687777adad2e5c160b9475c1d6448f))
* **04-01:** create base.html with sidebar and shared structure ([470e10a](https://github.com/cooksterj/lattice/commit/470e10a803f5019829fa6a8168c5fa2a7a0f2218))
* **04-02:** migrate asset_detail.html and asset_live.html to extend base.html ([92640d7](https://github.com/cooksterj/lattice/commit/92640d7d1c9b459ff8a52b2bbd802298f58ae801))
* **04-02:** migrate index.html and history.html to extend base.html ([2dad2ce](https://github.com/cooksterj/lattice/commit/2dad2ced8612c9d1e78d44c09f91251c1e7adceb))
* **05-01:** add /runs active runs page with dual-mode display ([4d26b1c](https://github.com/cooksterj/lattice/commit/4d26b1cba0b31e5452b2c34f64a61925a3b4d999))
* **05-02:** refactor asset_live.html from popup-style to full-page layout ([1b8d8c9](https://github.com/cooksterj/lattice/commit/1b8d8c9821fdf79603f65598d34e8dbc7932fb5f))
* **06-01:** implement graph selection and context-aware Execute button ([888aeff](https://github.com/cooksterj/lattice/commit/888aeff5838b53b327767b88b9b8d87626995e57))
* **07-01:** remove v1 popup infrastructure from graph.js ([7a4ac8c](https://github.com/cooksterj/lattice/commit/7a4ac8c6932fb742644b4e1e1f4cdd83ef320336))
* add failure recovery demo with retry support ([a70a26d](https://github.com/cooksterj/lattice/commit/a70a26d2bd918696e0514d8d618e000b10598597))
* Additional infrasture with the SQLite databases. ([206670d](https://github.com/cooksterj/lattice/commit/206670dd5ce6709a1e5bdd865a23bccfb3fc4e6c))
* archive v1.0 milestone ([f4a4729](https://github.com/cooksterj/lattice/commit/f4a4729a4900d9a9a79f7493c75f5b030480c2e6))
* Expose asset detail and log information with the asset window. ([8268369](https://github.com/cooksterj/lattice/commit/8268369d15ff95fbc76235a911458321e73d7895))
* Implement streaming infrastructure and per-asset WebSocket (Phase 1) ([e8a1b66](https://github.com/cooksterj/lattice/commit/e8a1b66225c7ef450044747c079cc028c0e2c333))
* Implementation of phase 7. ([a841abc](https://github.com/cooksterj/lattice/commit/a841abca8b0266628ed28e33af0e2d5c72e8bec0))
* targeted re-execution runs only selected asset and downstream ([9ff3ee1](https://github.com/cooksterj/lattice/commit/9ff3ee19d6a95b20a343f2b0e9b234845fca1a10))


### Bug Fixes

* propagate skipped status to downstream assets in async executor ([6579714](https://github.com/cooksterj/lattice/commit/6579714eb87d64e025145ab8cf0b091ffa0f5b5d))
* Use named window targeting for reliable refocus across browsers ([39d4eb2](https://github.com/cooksterj/lattice/commit/39d4eb2c21c53e8e0d277d7d67a894474dee9fce))


### Documentation

* **01:** create phase plan ([ce98a4a](https://github.com/cooksterj/lattice/commit/ce98a4a3625f07a87ac23e24905ee582ac10a83b))
* **02-01:** complete live monitoring page route and template plan ([c5028ab](https://github.com/cooksterj/lattice/commit/c5028abac30a686dc70c12727a27fd722cfd1ec9))
* **02-02:** complete WebSocket client with state machine plan ([f1149d2](https://github.com/cooksterj/lattice/commit/f1149d217bf53b4e197fd3dbbe016481f2dfad1c))
* **02-03:** complete completion-banner-and-action-buttons plan ([e5da942](https://github.com/cooksterj/lattice/commit/e5da942a05ec21e6f13a19f093886051affc7c9a))
* **02:** address plan checker feedback on route ordering and testing notes ([aceb127](https://github.com/cooksterj/lattice/commit/aceb1277041a74113c1d2acca10999a17386bc15))
* **02:** create phase plan ([7781e91](https://github.com/cooksterj/lattice/commit/7781e91229b86d859ae930ef89379092bf27cbf0))
* **03:** create phase plan ([c75d66c](https://github.com/cooksterj/lattice/commit/c75d66c6d745ab10a3bba16cd075ee34e154645b))
* **04-01:** complete template foundation & sidebar plan ([2b0f8a3](https://github.com/cooksterj/lattice/commit/2b0f8a3bfb58e49297997d9b16f44f4fb7eea220))
* **04-02:** complete template migration plan ([0dc84d4](https://github.com/cooksterj/lattice/commit/0dc84d44679ef3451341ecb8d9c31d36904f750b))
* **04:** complete template foundation & sidebar phase ([910b5dd](https://github.com/cooksterj/lattice/commit/910b5dd0ed698888243b2e347176453a5864f83a))
* **04:** create phase plan ([b2e662d](https://github.com/cooksterj/lattice/commit/b2e662d048cd5198a80efe1300a5a20099ce3c23))
* **05-01:** complete active runs page plan ([afcc635](https://github.com/cooksterj/lattice/commit/afcc6354406e3dd5c110d28365886b9484593a1d))
* **05-02:** complete asset live page refactor plan ([68b5a4d](https://github.com/cooksterj/lattice/commit/68b5a4d8b083b01bdfce5d27be3c5db5fdf77198))
* **05:** create phase plan for run monitoring & live logs ([1fedbd5](https://github.com/cooksterj/lattice/commit/1fedbd5bb5804a9f9394b9ccb7bec2b481b2e387))
* **05:** research phase domain ([960cbda](https://github.com/cooksterj/lattice/commit/960cbdabfdc59703a5fa660fc11675b749ad3af4))
* **06-01:** complete graph selection plan ([dc45cf7](https://github.com/cooksterj/lattice/commit/dc45cf7496a752f5583b63fc83462f43222bedb5))
* **06:** create phase plan for graph selection & failure recovery ([e004eec](https://github.com/cooksterj/lattice/commit/e004eec8cf6e61f2be3a8cb1bd611fde70256381))
* **06:** research phase domain ([8963db8](https://github.com/cooksterj/lattice/commit/8963db86bd68513876cfed4a97f2de8c2b036b22))
* **07-01:** complete popup cleanup plan - v2.0 milestone shipped ([55cdb17](https://github.com/cooksterj/lattice/commit/55cdb17b2a233f0e743fdfbbd5f6337be590e377))
* **07:** create phase plan ([19cc31d](https://github.com/cooksterj/lattice/commit/19cc31df31602428742b6a5068261e08a2056bff))
* complete v2.0 project research synthesis ([9a2cdc2](https://github.com/cooksterj/lattice/commit/9a2cdc25a537f21262baf3e2faabac7a6368c0a3))
* create roadmap (3 phases) ([99c3f18](https://github.com/cooksterj/lattice/commit/99c3f18bc65a2e09e1558af23e4c9409790d6811))
* create v2.0 roadmap (4 phases) ([211a5e3](https://github.com/cooksterj/lattice/commit/211a5e32473947a02f5a5c0a7f4c3cdb7e68060f))
* define v1 requirements ([8f5d73f](https://github.com/cooksterj/lattice/commit/8f5d73f8c8926ae99d988b04680f69e010e0eca0))
* define v2.0 milestone requirements ([e3a253f](https://github.com/cooksterj/lattice/commit/e3a253fd150b28caf2a7ec6b513df3a2425c62f9))
* domain research for multi-window asset monitoring ([a5f5210](https://github.com/cooksterj/lattice/commit/a5f5210335a74d120f7c54e9e5f47f0b53620bd9))
* initialize project ([5fde97e](https://github.com/cooksterj/lattice/commit/5fde97ead3f2125999a4ef560f0e67dfbffa2686))
* map existing codebase ([1318a73](https://github.com/cooksterj/lattice/commit/1318a7344b1be318f271ed01a595e5493ca15279))
* **phase-1:** research streaming infrastructure and WebSocket implementation ([96384a2](https://github.com/cooksterj/lattice/commit/96384a21d411b9f3f6048883636b77c87f893c0e))
* **phase-2:** complete asset live monitoring page phase ([f6d551f](https://github.com/cooksterj/lattice/commit/f6d551f2853160abc0f005275648ea808b19fdbd))
* **phase-2:** research phase domain ([c109135](https://github.com/cooksterj/lattice/commit/c109135379fb7e0678b27bccee90ca9f5666b6c5))
* **phase-3:** complete main graph window integration phase ([f2a61cb](https://github.com/cooksterj/lattice/commit/f2a61cb7c6812a237f71fe187d4802eb9ba4d2c5))
* **phase-3:** research main graph window integration ([3194ad3](https://github.com/cooksterj/lattice/commit/3194ad3572db7b3bf7eb0fef1392a3bc6609e83f))
* **phase-4:** research template foundation & sidebar ([3af3739](https://github.com/cooksterj/lattice/commit/3af37399324acf065f5ea3a6822409c119c309a4))
* **phase-6:** add phase verification report ([352bd08](https://github.com/cooksterj/lattice/commit/352bd083cdc30f8d2c8ddb1d5d9719a14ff9e853))
* **phase-7:** complete phase execution and verification ([7b5fe51](https://github.com/cooksterj/lattice/commit/7b5fe51a1b48b07e63df1285e8434f9c593359bf))
* **phase-7:** research phase domain ([0308a9c](https://github.com/cooksterj/lattice/commit/0308a9c2418b7081bbc9c97e339a96d1f9ffce79))
* start milestone v2.0 Sidebar Navigation & Failed Asset Recovery ([0a9eb9c](https://github.com/cooksterj/lattice/commit/0a9eb9cd79ee4990dc42419f998f811811d36067))

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
