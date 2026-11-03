# Third-party sources

Windflow is a collection of independently installable skills and an optional coordinator. Upstream methods are adapted and integrated by responsibility. The [version lock](upstream-lock.json) records the original source revisions and available blob hashes, not hashes of the adapted output.

| Windflow owner | Upstream material |
| --- | --- |
| investigate | pstack how and why |
| grill | Matt Pocock grilling |
| design | pstack arena and architect |
| write | pstack unslop and technical-writing |
| Agent coordination | pstack swarm |
| plan | Previously adapted specification and slicing ideas from Matt Pocock to-spec and to-tickets |
| Execution context | tt-a1i/matt-skills-with-to-goal to-spec, to-goal, and spec-executor |

## Revisions and adaptations

[Matt Pocock skills](https://github.com/mattpocock/skills/tree/3cca18b368ae95cdbdebbff572ccafa662551015) supplies the design-tree interview method and the previously adapted planning ideas. Windflow's implementation and review procedures are its own; it does not bundle Matt's implement or code-review.

[Lauren Tan pstack](https://github.com/cursor/plugins/tree/ae5650febf4320793844c12c4adaa937f417f8da/pstack) supplies the investigation, design comparison, architecture, parallel-work, and writing methods. Windflow uses native host tools and configured models. Design compares independent proposals and then converges in the same parent. Parallel isolation and evidence handling are integrated into relevant stages instead of exposed as a second orchestration skill.

[matt-skills-with-to-goal](https://github.com/tt-a1i/matt-skills-with-to-goal/tree/974c932292f0c7cca6481ea8029c17a7dd91b063) informs readiness markers and optional evidence-bearing handoffs. These do not authorize automatic task creation or add a mandatory goal stage.

Each adapted skill briefly names its source. Applicable MIT copyright notices are collected in this file, and the repository license is the root [LICENSE](LICENSE). The original upstream entrypoint names are preserved in attribution; they are not separate Windflow skill aliases. Upstream authors do not endorse Windflow's authorization, validation, or review policies.

## MIT notices

Copyright (c) 2026 Matt Pocock

Copyright (c) 2026 Lauren Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
