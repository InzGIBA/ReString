---
name: Research idea
about: Propose a measurable experiment in the project's format
labels: ["research"]
---

The project's research culture: every quality claim gets a measurement with pre-registered success bars before any code ships. Frame your idea the same way and it can become a task like the ones in [tasks/](../blob/main/tasks/).

**Question**

What do you want to know? One sentence, in the form "does X beat Y at equal Z?"

**Hypothesis**

What do you expect to happen, and through what mechanism?

**Pre-registered success bar**

What number adopts the idea, measured on what? Example from the backlog: "adopt only on a 5 percent or better color MSE improvement at an equal budget, on both portrait fixtures." State the bar before running anything; changing it after seeing the data is how dead ends get relitigated.

**Fixtures and metrics**

Which images (the two portrait fixtures in `tests/data/` are the standard), which metric (render MSE, center MSE, SSIM), which budget.

**Prior art**

Which of the existing measurements is closest? [docs/research/](../blob/main/docs/research/) holds the earlier ones; the search-strategy family (beam, horizon, multi-scale, asymmetric, local search, multi-start) is closed — the bar for reopening it is a mechanism those measurements did not cover.
