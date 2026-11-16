# Proxy helpers. The endpoint is resolved per call by `with-proxy`, which
# probes the port this device actually serves (Clash Verge 7897, managed mihomo
# 7890) and honours PROXY_HTTP. Nothing about the port is baked in at
# `chezmoi init`, so one dotfiles checkout serves a headless host and a desktop
# running a different client.

export def --env noproxy [] {
    let url = (^with-proxy --print-url | str trim)
    $env.http_proxy = $url
    $env.https_proxy = $url
    $env.HTTP_PROXY = $url
    $env.HTTPS_PROXY = $url
    $env.ALL_PROXY = ($url | str replace 'http://' 'socks5h://')
    $env.all_proxy = $env.ALL_PROXY
    $env.NO_PROXY = 'localhost,127.0.0.1,::1'
    $env.no_proxy = $env.NO_PROXY
}

# Compatibility for the old Nu-only name.
export def --env nuproxy [] { noproxy }

export def --env unproxy [] {
    hide-env --ignore-errors http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
}
