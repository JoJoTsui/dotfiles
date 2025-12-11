# Nushell Config File
#
# version = "0.103.0"


# STARSHIP
mkdir ($nu.data-dir | path join "vendor/autoload")
starship init nu | save -f ($nu.data-dir | path join "vendor/autoload/starship.nu")

# SHELL
source ~/joey/SHELL/.zoxide.nu
# environment is not available in config
# do not use 'source' in micromamba.nu
use ~/joey/SHELL/CLIs/nushell/micromamba.nu
# use ~/joey/SHELL/CLIs/nushell/conda.nu
# use 'source' in nu_scripts
source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/bat/bat-completions.nu
source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/btm/btm-completions.nu
source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/curl/curl-completions.nu
source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/git/git-completions.nu
# source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/less/less-completions.nu
source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/rg/rg-completions.nu
# source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/tar/tar-completions.nu
# source ~/joey/SHELL/CLIs/nushell/nu_scripts/custom-completions/zellij/zellij-completions.nu
source /t9k/mnt/joey/SHELL/CLIs/nushell/direnv.nu

source ~/joey/SHELL/CLIs/nushell/proxy.nu
