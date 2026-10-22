# Security reporting

Vesta currently targets a local, single-user environment. Its Sandbox,
tool-permission, MCP process, and secret-handling paths are security sensitive.
This project does not promise a security response SLA or a dedicated security
team.

If you find a vulnerability, use **Report a vulnerability** under this
repository's GitHub **Security** tab if that private channel is available.
Otherwise, contact the repository owner through a private channel listed on
their GitHub profile. If neither is available, open a public issue requesting
a private contact method **without** exploit details, secrets, or personal data.

Include affected commit or version, platform, reproduction steps, impact,
and a minimal proof of concept in the private report. Do not test against
systems or accounts you do not own. The maintainer will assess reports and
coordinate fixes as availability permits; disclosure timing is agreed case by
case. Do not assume a report has been received until it is acknowledged.

Known boundary: the native Sandbox backend is currently macOS Seatbelt. On
platforms without a supported backend, constrained Shell and MCP launches
should fail closed. Explicit Host mode weakens isolation and should be chosen
only with an understanding of that risk.
