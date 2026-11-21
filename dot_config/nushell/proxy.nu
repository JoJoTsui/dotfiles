# Proxy helpers for Nushell.
#
# The endpoint decision belongs to the POSIX launcher `with-proxy`: it owns the
# precedence, the health check, and the fallback. This adapter reads the answer
# from there, so a Nushell session and a Bash session route the same way and
# the shell a session runs in never changes where traffic goes.

# The variables the launchers own. `with-proxy` sets them for a child, and a
# direct launch clears them.
const proxy_variables = [
    HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
    ALL_PROXY all_proxy NO_PROXY no_proxy PROXY
]

# The inherited variables a direct launch clears for its child. The FTP
# spellings are never set by this deployment, but a parent may export them and
# the POSIX launcher clears them too.
const direct_proxy_variables = [
    HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
    ALL_PROXY all_proxy FTP_PROXY ftp_proxy
    NO_PROXY no_proxy PROXY
]

# The spellings a Nu session keeps. Nu's environment is case-insensitive, so
# only one spelling of a variable survives; these are the ones the session has
# always used. A launched child still receives every spelling, because the
# shared launcher applies them in a POSIX environment.
const session_variables = [http_proxy https_proxy ALL_PROXY NO_PROXY PROXY]

# Parse the KEY=VALUE lines the shared launcher prints into a record. Only the
# variables the launchers own are accepted, so a value that carries a newline
# cannot add a variable of its own.
def parse-proxy-environment [lines: list<string>] {
    $lines | where {|line| ($line | str trim) != "" } | reduce --fold {} {|line, environment|
        let parts = ($line | split row "=")
        let name = ($parts | first)
        if $name in $proxy_variables {
            $environment | upsert $name ($parts | skip 1 | str join "=")
        } else {
            $environment
        }
    }
}

# The environment the shared launcher resolved. The launcher answers with the
# variables it owns, so this adapter reads them instead of rebuilding them.
def proxy-environment [] {
    let resolved = (^with-proxy --print-env | complete)
    if $resolved.exit_code != 0 {
        error make {msg: "with-proxy did not answer the endpoint decision"}
    }
    parse-proxy-environment ($resolved.stdout | lines)
}

# Apply the shared proxy environment to this session: the same endpoint, the
# same overrides, and the same values the POSIX shell helper applies.
export def --env noproxy [] {
    load-env ((proxy-environment) | select ...$session_variables)
}

# Compatibility for the old Nu-only name.
export def --env nuproxy [] { noproxy }

# Clear the supported proxy variables for this session, the same list the
# POSIX `direct` launcher and the direct fallback clear.
export def --env unproxy [] {
    hide-env --ignore-errors ...$direct_proxy_variables
}

# Run a command through the shared launcher, so the child gets exactly what the
# POSIX launcher gives it: the same endpoint, every spelling of the variables,
# the same direct fallback, and the same exit status. A leading
# `--if-available` asks for that fallback: without a healthy endpoint the
# child runs without the inherited proxy variables.
export def --wrapped with-proxy [...args] {
    ^with-proxy ...$args
}

# Run a command without any proxy variable, the counterpart of the POSIX
# `direct` launcher. The child sees a clean environment; the session is
# unchanged.
export def --wrapped direct [...args] {
    ^direct ...$args
}
