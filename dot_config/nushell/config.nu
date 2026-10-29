# Paths are relative to this source file so native adapters can deploy this
# complete directory at the platform's discovery location. Nothing is fetched
# or generated during startup; optional generated hooks use Nu vendor autoload.
use micromamba.nu *
source direnv.nu
source proxy.nu
source zoxide.nu

def --wrapped logs [...arguments: string] {
    if ($in | is-empty) { ^tspin ...$arguments } else { $in | ^tspin ...$arguments }
}

const local_config_path = ($nu.home-dir | path join .config dotfiles nu.local.nu)
const local_config = if ($local_config_path | path exists) { $local_config_path } else { null }
source $local_config
