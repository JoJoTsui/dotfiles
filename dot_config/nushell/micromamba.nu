export-env {
    # Shared managed paths and deliberate device overrides come from env.nu.
    
    # Initialize state variables if they don't exist
    if not ("CONDA_CURR" in $env) { $env.CONDA_CURR = null }
}

# Helper: Get environments only when needed
def get-conda-envs [] {
    let raw_info = (if ($env.MAMBA_EXE? | is-not-empty) {
        ^$env.MAMBA_EXE env list --json
    } else {
        error make {msg: "MAMBA_EXE is unset; load the managed env.nu first"}
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

# Nu cannot source Bash/cmd activation hooks. Refuse those environments rather
# than claiming activation succeeded; micromamba run supports their native hooks.
def environment-variables [prefix: path] {
    for hook in [activate.d deactivate.d] {
        let directory = ($prefix | path join etc conda $hook)
        if ($directory | path exists) and ((ls -a $directory | length) > 0) {
            error make {msg: $"This environment needs ($hook) hooks. Use micromamba run -p '($prefix)' <command>, or activate it in Bash/Zsh."}
        }
    }
    mut variables = {}
    let packages = ($prefix | path join etc conda env_vars.d)
    if ($packages | path exists) {
        for file in (ls $packages | where name ends-with '.json' | sort-by name) {
            $variables = ($variables | merge (open --raw $file.name | from json))
        }
    }
    let state = ($prefix | path join conda-meta state)
    if ($state | path exists) {
        $variables = ($variables | merge (open --raw $state | from json | get -o env_vars | default {}))
    }
    for item in ($variables | transpose name value) {
        if ($item.name !~ '^[A-Za-z_][A-Za-z0-9_]*$') or (($item.value | describe) != 'string') {
            error make {msg: 'Conda environment variables must have valid names and string values'}
        }
        if $item.name in [PATH Path CONDA_OLD_PATH DOTFILES_CONDA_SAVED CONDA_CURR CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_SHLVL CONDA_PROMPT_MODIFIER] {
            error make {msg: $"Unsupported Conda environment override: ($item.name). Use micromamba run."}
        }
    }
    $variables
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
    let variables = (environment-variables $target_path)
    let names = ($variables | columns)
    $env.DOTFILES_CONDA_SAVED = ({
        values: ($env | select -o ...$names)
        missing: ($names | where {|key| $key not-in $env })
    } | to nuon)
    
    # SNAPSHOT: Save PATH
    $env.CONDA_OLD_PATH = $env.PATH

    # Detect OS
    let is_windows = ((sys host).name == "Windows")
    let bin_path = if $is_windows {
        [$target_path,
         ($target_path | path join Library mingw-w64 bin),
         ($target_path | path join Library usr bin),
         ($target_path | path join Library bin),
         ($target_path | path join Scripts),
         ($target_path | path join bin)]
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
    for item in ($variables | transpose name value) {
        if $item.value == '***unset***' { hide-env -i $item.name } else { load-env { $item.name: $item.value } }
    }
}


export def --env deactivate [] {
    # Check if ANY Conda variable is set (more robust)
    let is_active = ($env.CONDA_DEFAULT_ENV? | is-not-empty) or ($env.CONDA_CURR? | is-not-empty)

    if not $is_active {
        print "No Conda/Mamba environment is active."
        return
    }

    if ($env.DOTFILES_CONDA_SAVED? | is-not-empty) {
        let saved = ($env.DOTFILES_CONDA_SAVED | from nuon)
        for key in $saved.missing { hide-env -i $key }
        load-env $saved.values
        hide-env DOTFILES_CONDA_SAVED
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
