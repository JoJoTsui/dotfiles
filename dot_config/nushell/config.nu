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

# Herdr panes use an in-process Codex app server so hooks inherit the pane
# identity. Importing from a module lets device-local definitions shadow this
# command without creating duplicate definitions in the same lexical block.
module dotfiles-codex {
    export def --wrapped codex [...args] {
        if ($env.HERDR_ENV? == "1") {
            ^codex-herdr ...$args
        } else {
            ^codex ...$args
        }
    }
}
use dotfiles-codex codex

const local_config_path = ($nu.home-dir | path join .config dotfiles nu.local.nu)
const local_config = if ($local_config_path | path exists) { $local_config_path } else { null }
source $local_config
