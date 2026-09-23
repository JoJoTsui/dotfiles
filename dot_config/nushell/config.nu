# Nushell Config File
#
# version = "0.103.0"



mkdir $"($nu.data-dir)/vendor/autoload"
pixi completion --shell nushell | save --force $"($nu.data-dir)/vendor/autoload/pixi-completions.nu"



# STARSHIP
mkdir ($nu.data-dir | path join "vendor/autoload")
starship init nu | save -f ($nu.data-dir | path join "vendor/autoload/starship.nu")

# SHELL — zoxide is generated into vendor/autoload by env.nu and auto-loaded;
# micromamba.nu / direnv.nu / proxy.nu live next to this file.
# environment is not available in config
# do not use 'source' in micromamba.nu
use ~/.config/nushell/micromamba.nu
# use ~/.config/nushell/conda.nu
# use 'source' in nu_scripts (cloned to ~/.config/nushell/nu_scripts by bootstrap.sh)
source ~/.config/nushell/nu_scripts/custom-completions/bat/bat-completions.nu
source ~/.config/nushell/nu_scripts/custom-completions/curl/curl-completions.nu
source ~/.config/nushell/nu_scripts/custom-completions/git/git-completions.nu
source ~/.config/nushell/nu_scripts/custom-completions/rg/rg-completions.nu
source ~/.config/nushell/direnv.nu

source ~/.config/nushell/proxy.nu
