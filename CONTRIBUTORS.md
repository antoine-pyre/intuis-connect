# Contributors and contribution sources

Created and maintained by [Antoine Pyré / antoine-pyre](https://github.com/antoine-pyre).

The following list records contributors and proposals reviewed for this project.
Acknowledging a proposal does not imply that it was merged or shipped. This is
a source register for the reviewed PRs, not an exhaustive list of everyone who
has helped through commits, reviews, reports or testing.

| Contributor | Contributions and proposals | Current status |
|---|---|---|
| [tranb3r](https://github.com/tranb3r) | [#2 — repository URL](https://github.com/antoine-pyre/intuis-connect/pull/2) | Proposal acknowledged; the manual installation URL is already corrected in the current project |
| [halfred](https://github.com/halfred) | [#5 — missing schedule temperatures](https://github.com/antoine-pyre/intuis-connect/pull/5) | Proposal acknowledged; the current parser handles absent/malformed data differently |
| [chrislek](https://github.com/chrislek) | [#11 — event schedules / Aqua Manager](https://github.com/antoine-pyre/intuis-connect/pull/11) | Merged; event schedule parsing is present |
| [Sylvain REMY / sremy91](https://github.com/sremy91) | [#13 — sensor updates](https://github.com/antoine-pyre/intuis-connect/pull/13), [#15 — climate presets, heating and counters](https://github.com/antoine-pyre/intuis-connect/pull/15), [#16 — workflow and related fixes](https://github.com/antoine-pyre/intuis-connect/pull/16) | #13 and #15 merged; #16 closed, with its needs covered by the current code |
| [TheFab21](https://github.com/TheFab21) | [#12 — temperature statistics](https://github.com/antoine-pyre/intuis-connect/pull/12), [#17 — initial hourly/planning proposal](https://github.com/antoine-pyre/intuis-connect/pull/17), [#22 — hourly energy, costs and HTML planning](https://github.com/antoine-pyre/intuis-connect/pull/22), [#24 — planning fixes and bundled distribution](https://github.com/antoine-pyre/intuis-connect/pull/24) | #12 merged; #17 superseded; extended planning services, hourly energy statistics, energy costs and the bundled HTML planning editor (also from #17) adapted from #22/#24 locally (unreleased) |

## Sources for planned adaptations

- #22: `3174384d9222bdca5310721940ece95fe6d1fce6`.
- #24: `fb39b93c1eaf2a498c7274210b566864a2497669`.
- Earlier #17: `75ae980bd22c98b3fa42bb9f933c044d2c648c58`.

See the [integration plan](docs/pr-integration-plan.md) for coverage, attribution
rules and delivery status. Each delivered lot must record the actual code/ideas
adapted, revision and implementation commits, including any additional authors.

## Related community work

[adrienvsj](https://github.com/adrienvsj) maintains a
[community fork](https://github.com/adrienvsj/intuis-connect) and shared fixes in
[#28](https://github.com/antoine-pyre/intuis-connect/issues/28) and PR discussions.
[apeyrat](https://github.com/apeyrat) proposed pilot-wire support in
[#27](https://github.com/antoine-pyre/intuis-connect/issues/27).
These are acknowledged separately from the ten PRs covered by this plan.
Any code actually adapted from these sources must retain its own provenance;
no such adaptation is claimed as delivered here.

## Attribution when adapting a contribution

Preserve original authorship when reusing a commit unchanged. For rewritten or
adapted work, keep the adaptation author's identity and include the actual source:

```text
Adapted-from: https://github.com/antoine-pyre/intuis-connect/pull/22
Original-author: @TheFab21
```

Use a Co-authored-by trailer only with an established coauthor identity and actual
coauthorship; do not invent an email from a login. Link the source in release
notes and the delivery description, retain existing copyright/license notices,
and keep the root [MIT license](LICENSE). Keep the creator credit above.


## Verified PR revisions — 26 October 2026

- [#2](https://github.com/antoine-pyre/intuis-connect/pull/2): `66ee8d6df07a2714128741cb9b3a66c61e3139b3`.
- [#5](https://github.com/antoine-pyre/intuis-connect/pull/5): `cbe69765a9d20ef6d25d6302d10f23881211c8aa`.
- [#11](https://github.com/antoine-pyre/intuis-connect/pull/11): `4b72822a979d52f15e637a15083bc238d2908472`.
- [#12](https://github.com/antoine-pyre/intuis-connect/pull/12): `d8c411015eb5f7d03b5cdbfbd535b1765a2d29e0`.
- [#13](https://github.com/antoine-pyre/intuis-connect/pull/13): `8d5a2c3e0fdbae0a8d79d2a9bd4f82d329a55344`.
- [#15](https://github.com/antoine-pyre/intuis-connect/pull/15): `d8973de4e01205c4e538f9101d78886ebe928014`.
- [#16](https://github.com/antoine-pyre/intuis-connect/pull/16): `987a6ccc39f5e0a768136e4b2bee810646a2d42d`.
- [#17](https://github.com/antoine-pyre/intuis-connect/pull/17): `75ae980bd22c98b3fa42bb9f933c044d2c648c58`.
- [#22](https://github.com/antoine-pyre/intuis-connect/pull/22): `3174384d9222bdca5310721940ece95fe6d1fce6`.
- [#24](https://github.com/antoine-pyre/intuis-connect/pull/24): `fb39b93c1eaf2a498c7274210b566864a2497669`.
