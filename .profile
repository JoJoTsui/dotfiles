# ~/.profile: executed by the command interpreter for login shells.

# if running bash, include .bashrc
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi



# Launch nushell for login shells only
if [ -n "${GIZMO}" ] && [ -z "${NU_VERSION}" ]; then
    export SHELL="${GIZMO}/nushell/nu"
    exec "${SHELL}" -l
fi
