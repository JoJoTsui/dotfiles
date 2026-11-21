---
status: accepted
---

# Let one launcher own the proxy endpoint decision

A session could disagree with itself about where traffic goes. The POSIX
`with-proxy` resolved an endpoint per call, but the Nushell `noproxy` asked for
the URL alone and rebuilt the variable set by hand: it ignored `PROXY_NO` and
`PROXY_SOCKS`, it never set `PROXY`, and its `unproxy` cleared six variables
where the POSIX `direct` cleared eleven. The same device therefore routed
differently depending on the shell, and a stale inherited `http_proxy`
survived a `unproxy` in one shell and not in the other.

`with-proxy` now owns the whole decision: the precedence (an explicit
`PROXY_HTTP`, then the probed ports 7897 and 7890, then the ordinary
fallback), the health check, the supported overrides (`PROXY_HTTP`,
`PROXY_SOCKS`, `PROXY_NO`), and the variable set. It answers in two shapes:
POSIX export lines (`--print`) and `KEY=VALUE` lines (`--print-env`), so an
adapter can consume the answer without copying the port list.

The Nushell adapter is a thin adapter over that answer. Its session helpers
`noproxy` and `unproxy` read the shared variables and clear the supported
inherited ones, and its launchers run the child through the shared launcher,
so a child receives the same environment, the same direct fallback, and the
same exit status whichever shell started it.

The direct fallback clears the supported inherited proxy variables for the
child only, including the FTP spellings the deployment never sets, and a
proxied launch applies its environment to the child only. The calling session
keeps its own environment, and the child's arguments and exit status are
unchanged.

Nushell's environment is case-insensitive, so a Nu session holds one spelling
of a variable where a POSIX session holds two. The session helpers keep the
spellings they always kept; a launched child receives every spelling, because
the shared launcher applies them in a POSIX environment. A launcher that
rebuilt the environment inside Nushell could not deliver both spellings, which
is why the adapter runs the child through the shared launcher instead.

Consequence: the launchers cannot drift apart without a change to
`with-proxy` itself, and the checks compare what a child actually receives
rather than what a helper intends.
