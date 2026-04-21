# Security

## Overview

Canopus is a local-first CLI assistant runtime. It executes capabilities, plugins,
and workflows on the user's machine. Because it can invoke file system operations,
shell-adjacent tools, and user-defined plugins, security hygiene matters.

This document describes how to report vulnerabilities and how to use Canopus
responsibly.

---

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

To report a vulnerability privately:

1. Go to the repository on GitHub:
   [https://github.com/Gamecooler19/Canopus](https://github.com/Gamecooler19/Canopus)
2. Click **Security** → **Report a vulnerability** (GitHub private security advisory).
3. Describe the vulnerability clearly: what it is, how to reproduce it, and what
   the potential impact is.

There is no SLA or guaranteed response time. Canopus is maintained by a single
developer and is not a production service. You will receive a response when available.
Sensitive reports will be handled discretely.

---

## Scope

The following are in scope for security reports:

- Capability execution bypassing policy or permission checks
- Plugin loading that allows arbitrary code execution beyond documented plugin contracts
- Secrets or credentials leaking through traces, logs, or memory records
- Path traversal or injection in file-system capabilities
- MCP server configurations being used to execute unintended commands

The following are **out of scope** for this project's security model:

- Attacks that require physical access to the machine
- Vulnerabilities in third-party dependencies (report to the relevant upstream project)
- Social engineering or phishing

---

## Security model and assumptions

Canopus is designed for **single-user, local operation**. It assumes:

- The user running Canopus is the owner of the machine and the `~/.canopus/` directory
- Plugins placed in `~/.canopus/plugins/` are trusted by the user who placed them there
- MCP servers configured in `~/.canopus/config/config.toml` are trusted
- Workflow YAML files from the user's `~/.canopus/workflows/` are trusted

**Canopus does not sandbox plugins or MCP servers.** A plugin file that is placed in
the plugins directory will be imported and executed. Users must only install plugins
from sources they trust.

---

## Secrets and sensitive data

- Never put secrets (API keys, passwords, tokens) directly in workflow YAML files
- Use `~/.canopus/config/secrets.toml` (when implemented) for secret storage
- Trace files in `~/.canopus/traces/` contain execution records; review before sharing
- Memory records in `~/.canopus/memory/` may contain sensitive context; protect the directory

---

## Capability permissions

Every capability declares its permission requirements in its `CapabilitySpec`. The
policy layer checks these before execution. Capabilities with destructive side effects
(e.g. `fs.write`, `shell.exec`) should require explicit confirmation policies.

When adding capabilities or plugins, assign the most restrictive permission set that
still allows the capability to function.

---

## Responsible use

Canopus is capable of executing real actions on real systems. Use caution when:

- Connecting to MCP servers that expose shell or network capabilities
- Running workflows that invoke `fs.write` or similar capabilities
- Using model-generated plans without review

Model outputs are nondeterministic. The capability and policy layer exists specifically
to prevent model-generated instructions from bypassing your intent.

---

## No warranty

Canopus is provided as-is under the MIT License. There is no warranty, implied or
explicit, and no guarantee of security or fitness for any particular purpose.
See [LICENSE](LICENSE).
