---
title: Validate scaffolds in clean Linux and live Compose
date: 2026-07-11
category: tooling-decisions
module: monorepo-scaffold
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "Adding or changing cross-platform lockfiles, Dockerfiles, or Compose healthchecks"
tags:
  - docker-compose
  - npm-lockfile
  - healthchecks
  - reproducibility
---

# Validate scaffolds in clean Linux and live Compose

## Context

RIS-5 initially passed local application tests and static Compose parsing but still failed clean container builds and startup. A package lock generated with an existing Windows `node_modules` tree omitted Linux optional packages, and current PostgreSQL and Neo4j images had startup contracts that static YAML validation could not exercise.

## Guidance

Treat scaffold validation as three distinct gates:

1. Generate and verify lockfiles in a clean environment for the CI/container platform. For npm, run `npm ci` inside the Linux image used by CI rather than trusting an existing local install.
2. Run `docker compose config` to catch interpolation and schema errors.
3. Run `docker compose up --build --detach --wait` from clean disposable volumes and require every service healthcheck to pass. Probe the public backend and frontend endpoints after Compose reports healthy.

Pin image digests and GitHub Actions to immutable revisions once the full stack passes. Keep data-service ports bound to localhost for developer access, and quote credentials inside shell-based healthchecks.

## Why This Matters

Local unit tests prove application code, while clean installs prove lockfile completeness and live health gates prove image entrypoints, volume paths, networking, startup ordering, and probe behavior. None of these checks substitutes for the others.

## When to Apply

- Adding a dependency or regenerating a lockfile on a different operating system than CI.
- Changing Docker base images or datastore versions.
- Adding or editing Compose environment variables, volumes, dependencies, or healthchecks.
- Establishing a new repository baseline that future tickets depend on.

## Examples

The RIS-5 validation loop caught and fixed:

- Missing Linux `@emnapi/*` optional packages in a Windows-generated npm lockfile.
- PostgreSQL 18's required `/var/lib/postgresql` volume mount.
- Neo4j's strict handling of extra `NEO4J_*` environment variables.
- An IPv6 `localhost` mismatch in the frontend healthcheck.
- A backend container command that depended on an uninstalled optional FastAPI CLI.

CI now repeats the static Compose check and both container builds on every pull request.

## Related

- [RIS-5 implementation plan](../../plans/2026-07-11-ris-5-scaffold-plan.md)
- [PR #22](https://github.com/tomiwaaluko/risk-weave/pull/22)
