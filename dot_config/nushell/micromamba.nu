export-env {
    # Only set static variables here (FAST)
    # We assume standard paths, or you can hardcode them to save 'which' calls
    $env.MAMBA_EXE = ($env.JOEY | path join "gizmo" "micromamba")
    $env.MAMBA_ROOT_PREFIX = ($env.JOEY | path join "micromamba")
    
    # Initialize state variables if they don't exist
    if not ("CONDA_CURR" in $env) { $env.CONDA_CURR = null }
}

# Helper: Get environments only when needed
def get-conda-envs [] {
    let raw_info = (if not (which micromamba | is-empty) {
        micromamba env list --json
    } else {
        conda info --envs --json
    }) 
    
    let info = ($raw_info | from json)
    
    # FIXED: Used ? instead of get -i
    let root = ($info.root_prefix? | default $env.MAMBA_ROOT_PREFIX)

    # Transform into a simple record: { name: path }
    $info.envs | reduce -f {} {|it, acc|
        if $it == $root {
            $acc | upsert "base" $it
        } else {
            $acc | upsert ($it | path basename) $it
        }
    }
}

# 1. We add a completion function so pressing TAB works
def "nu-complete conda-envs" [] {
    get-conda-envs | columns
}

# 2. Add Type Signature and Completions to activate
export def --env activate [
    name: string@"nu-complete conda-envs"
] {
    let available_envs = (get-conda-envs)

    if not ($name in $available_envs) {
        print $"Environment '($name)' not found."
        return
    }

    # Safety: Check if already active
    if ($env.CONDA_DEFAULT_ENV? | is-not-empty) {
        print $"Environment '($env.CONDA_DEFAULT_ENV)' is already active. Deactivate first."
        return
    }

    let target_path = ($available_envs | get $name)
    
    # SNAPSHOT: Save PATH
    $env.CONDA_OLD_PATH = $env.PATH

    # Detect OS
    let is_windows = ((sys host).name == "Windows")
    let bin_path = if $is_windows {
        [$target_path, ($target_path | path join "Scripts")]
    } else {
        [$target_path, ($target_path | path join "bin")]
    }

    # SET ENV VARS
    load-env {
        PATH: ($env.PATH | prepend $bin_path)
        Path: ($env.PATH | prepend $bin_path) # Windows compat
        CONDA_CURR: $name
        CONDA_PREFIX: $target_path
        CONDA_DEFAULT_ENV: $name # Crucial for Starship
        CONDA_SHLVL: "1"
        CONDA_PROMPT_MODIFIER: $"($name)"
    }
}


export def --env deactivate [] {
    # Check if ANY Conda variable is set (more robust)
    let is_active = ($env.CONDA_DEFAULT_ENV? | is-not-empty) or ($env.CONDA_CURR? | is-not-empty)

    if not $is_active {
        print "No Conda/Mamba environment is active."
        return
    }

    # 1. Restore PATH
    if "CONDA_OLD_PATH" in $env {
        $env.PATH = $env.CONDA_OLD_PATH
        $env.Path = $env.CONDA_OLD_PATH
        hide-env CONDA_OLD_PATH
    } else {
        print "Warning: Could not restore original PATH (Snapshot missing)."
    }

    # 2. Nuke Environment Variables (The Starship Fix)
    # We use ignore-errors (?) because some might not exist
    hide-env CONDA_CURR
    hide-env CONDA_PREFIX
    hide-env CONDA_DEFAULT_ENV
    hide-env CONDA_SHLVL
    hide-env CONDA_PROMPT_MODIFIER
}


export def list-env [] {
    # 1. Determine active env (Fallback to 'base')
    let active_name = if ($env.CONDA_CURR? | is-not-empty) {
        $env.CONDA_CURR
    } else if ($env.CONDA_DEFAULT_ENV? | is-not-empty) {
        $env.CONDA_DEFAULT_ENV
    } else {
        "base"
    }

    get-conda-envs
    | transpose name path
    | sort-by name  # Sort FIRST, before adding color codes
    | insert Active {|row| 
        if $row.name == $active_name { 
            $"(ansi green_bold)*" 
        } else { 
            "" 
        } 
    }
    | update name {|row| 
        if $row.name == $active_name { 
            # Color the name Green Bold, then reset
            $"(ansi green_bold)($row.name)(ansi reset)" 
        } else { 
            $row.name 
        } 
    }
    | move Active --after name
    | table -e
}
