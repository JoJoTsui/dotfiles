{
    // --------------------------------------------------------
    // ⚡ CRITICAL FIXES (Shell & Watcher Limits)
    // --------------------------------------------------------
    "terminal.integrated.defaultProfile.linux": "bash",
    "terminal.integrated.env.linux": {
        "SHELL": "/bin/bash",           // Fixes Claude Code "STDIN" crash
        "CHOKIDAR_USEPOLLING": "1",     // Fixes Docker "ENOSPC" crash
        "UV_PYTHON_PREFERENCE": "only-system" // Optional: Stop uv from downloading python if you want to use system python
    },

    // --------------------------------------------------------
    // 🦀 MODERN RUST TOOLCHAIN (uv, ruff, ty)
    // --------------------------------------------------------
    
    // UV: The Package Manager
    // UV always creates venvs in .venv by default, simpler than conda
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    
    // RUFF: The Linter & Formatter (Replaces Black/Isort)
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",    // Auto-fix errors
            "source.organizeImports": "explicit" // Auto-sort imports
        }
    },
    "ruff.nativeServer": "on",  // Use the Rust binary (instant)

    // TY: The Type Checker (Replaces Pylance/MyPy)
    // If you have the 'ty' extension installed, this replaces Pylance
    "python.languageServer": "None", // Disable Pylance to save RAM
    "ty.enabled": true,              // Enable Astral's 'ty' LSP
    "ty.typeCheckingMode": "standard",

    // --------------------------------------------------------
    // 📡 NETWORK & PATHS
    // --------------------------------------------------------
    "http.proxy": "http://10.233.17.241:3128",
    "http.proxySupport": "override",

    // Static path avoids breaking when fnm version changes
    // RECOMMENDATION: Create a symlink `ln -s .../bin/claude ~/claude-bin` and use that here
    "claudeCode.claudeProcessWrapper": "/t9k/mnt/.local/state/fnm_multishells/2355227_1766469928757/bin/claude"
}
