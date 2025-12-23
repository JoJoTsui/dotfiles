#!/bin/bash

# Core environment shared with nushell (set before interactive check)
[ -f "$HOME/.env_core" ] && . "$HOME/.env_core"

# user rwx settings
umask 0022

# fnm node
eval "$(fnm env --use-on-cd --shell bash)"

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac


# >>> mamba initialize >>>
# !! Contents within this block are managed by 'micromamba shell init' !!
export MAMBA_EXE='/t9k/mnt/joey/gizmo/micromamba';
export MAMBA_ROOT_PREFIX='/t9k/mnt/joey/micromamba';
__mamba_setup="$("$MAMBA_EXE" shell hook --shell bash --root-prefix "$MAMBA_ROOT_PREFIX" 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__mamba_setup"
else
    alias micromamba="$MAMBA_EXE"  # Fallback on help from micromamba activate
fi
unset __mamba_setup
# <<< mamba initialize <<<

# starship
eval "$(starship init bash)"
# zoxide
eval "$(zoxide init bash)"
# direnv
eval "$(direnv hook bash)"
# Set up fzf key bindings and fuzzy completion
eval "$(fzf --bash)"
