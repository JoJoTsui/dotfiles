#!/bin/bash

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# JOEY environment
JOEY="/t9k/mnt/joey"
GIZMO="${JOEY}/gizmo"
BIO_GIZO="${JOEY}/bio_gizmo"

# user rwx settings
umask 0022

# PATH configuration
# [ -d "$HOME/bin" ] && PATH="$HOME/bin:$PATH"
[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin:$PATH"

