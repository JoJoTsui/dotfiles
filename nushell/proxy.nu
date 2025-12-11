export def --env nuproxy [] {
    $env.http_proxy = "http://10.233.17.241:3128"
    $env.https_proxy = "http://10.233.17.241:3128"
    $env.HTTP_PROXY = "http://10.233.17.241:3128"
    $env.HTTPS_PROXY = "http://10.233.17.241:3128"
}

export def --env unproxy [] {
    $env.http_proxy = ""
    $env.https_proxy = ""
    $env.HTTP_PROXY = ""
    $env.HTTPS_PROXY = ""
}