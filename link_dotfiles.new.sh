#!/usr/bin/env bash

# Dotfiles linking script
# This script creates symbolic links from home directory to dotfiles in ~/joey/SHELL/
# It backs up existing files/directories before creating links

set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# Configuration
DOTFILES_DIR="$HOME/joey/SHELL"
BACKUP_SUFFIX=".bak"

# Color codes and logging functions
declare -A COLORS=([RED]='\033[0;31m' [GREEN]='\033[0;32m' [YELLOW]='\033[1;33m' [BLUE]='\033[0;34m' [NC]='\033[0m')

log_info() { echo -e "${COLORS[BLUE]}[INFO]${COLORS[NC]} $1"; }
log_success() { echo -e "${COLORS[GREEN]}[SUCCESS]${COLORS[NC]} $1"; }
log_warning() { echo -e "${COLORS[YELLOW]}[WARNING]${COLORS[NC]} $1"; }
log_error() { echo -e "${COLORS[RED]}[ERROR]${COLORS[NC]} $1"; }

# Function to create symbolic link with backup
link_dotfile() {
    local source="$1" target="$2" _type="$3"  # 'file' or 'dir' - kept for documentation
    
    [[ ! -e "$source" ]] && { log_warning "Source $source does not exist, skipping"; return 1; }
    
    # Backup existing target if it exists and is not already a symlink to our source
    if [[ -e "$target" || -L "$target" ]]; then
        if [[ -L "$target" && "$(readlink "$target")" == "$source" ]]; then
            log_info "$target already linked correctly"
            return 0
        fi
        
        local backup="${target}${BACKUP_SUFFIX}"
        log_info "Backing up $target to $backup"
        mv "$target" "$backup"
    fi
    
    # Create symbolic link
    log_info "Linking $source -> $target"
    ln -sf "$source" "$target"
    log_success "Successfully linked $target"
}

# Function to link a file
link_file() {
    local filename="$1"
    link_dotfile "${DOTFILES_DIR}/${filename}" "${HOME}/${filename}" "file"
}

# Function to link a directory
link_directory() {
    local dirname="$1"
    link_dotfile "${DOTFILES_DIR}/${dirname}" "${HOME}/${dirname}" "dir"
}

# Main function
main() {
    log_info "Starting dotfiles linking process..."
    log_info "Dotfiles directory: $DOTFILES_DIR"
    
    [[ ! -d "$DOTFILES_DIR" ]] && { log_error "Dotfiles directory $DOTFILES_DIR does not exist!"; exit 1; }
    
    echo
    log_info "Linking configuration files..."
    
    # Configuration files
    for file in .env_core .bashrc .gitconfig .netrc .Rprofile .profile .condarc; do
        link_file "$file"
    done
    
    echo
    log_info "Linking configuration directories..."
    
    # Configuration directories
    for dir in .config .local .ssh .cache; do
        link_directory "$dir"
    done
    
    echo
    log_info "Linking development tool directories..."
    
    # Development tools
    for dir in .ipython .jupyter .cargo .rustup .aspera .npm .aws; do
        link_directory "$dir"
    done
    
    echo
    log_info "Linking VS Code directories..."
    
    # VS Code
    for dir in .vscode-server .vscode-server-insiders; do
        link_directory "$dir"
    done
    
    echo
    log_info "Linking Trae AI directories..."
    
    # Trae AI tools
    for dir in .trae-aicc .trae-server; do
        link_directory "$dir"
    done
    link_dotfile "${DOTFILES_DIR}/ai_completion" "${HOME}/ai_completion" "dir"
    

    echo
    log_info "Linking Other directories..."
    
    # Other tools
    for dir in .claude .gemini .nextflow .kiro-server; do
        link_directory "$dir"
    done

    echo
    log_info "Linking System configs..."
    
    # System configs
    [ -f /etc/bash.bashrc ] && sudo mv /etc/bash.bashrc /etc/bash.bashrc.bak; sudo ln -ns ~/joey/SHELL/bash.bashrc /etc

    echo
    log_success "Dotfiles linking completed successfully!"
}

# Help function
show_help() {
    cat << EOF
Dotfiles Linking Script

Usage: $0 [OPTIONS]

Options:
    -h, --help     Show this help message
    -n, --dry-run  Show what would be done without making changes

This script creates symbolic links from your home directory to dotfiles
stored in $DOTFILES_DIR. Existing files are backed up with a .bak suffix.
EOF
}

# Parse command line arguments and run
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help; exit 0 ;;
        -n|--dry-run) DRY_RUN=true; shift ;;
        *) log_error "Unknown option: $1"; show_help; exit 1 ;;
    esac
done

[[ "$DRY_RUN" == "true" ]] && log_info "DRY RUN MODE - No changes will be made"

main
