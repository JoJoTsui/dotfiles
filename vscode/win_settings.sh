{
    // --------------------------------------------------------
    // 🎨 VIBE CODING AESTHETICS (Flow State)
    // --------------------------------------------------------
    "editor.fontFamily": "'CaskaydiaMono Nerd Font', 'Fira Code', Consolas, monospace",
    "editor.fontLigatures": true,
    "editor.fontSize": 14,
    "editor.lineHeight": 1.6,
    "editor.cursorBlinking": "smooth",
    "editor.cursorSmoothCaretAnimation": "on",
    "editor.smoothScrolling": true,
    "editor.minimap.enabled": false,       // Remove visual noise
    "editor.renderWhitespace": "selection",
    "window.commandCenter": false,
    "workbench.layoutControl.enabled": false,

    // --------------------------------------------------------
    // 🤖 AI AGENTS & COPILOT
    // --------------------------------------------------------
    "github.copilot.nextEditSuggestions.enabled": true,
    "github.copilot.editor.enableAutoCompletions": true,
    "github.copilot.chat.customOAIModels": {
        "GLM-4.6": {
            "name": "GLM-4.6",
            "url": "https://open.bigmodel.cn/api/coding/paas/v4",
            "toolCalling": true,
            "thinking": true,
            "maxInputTokens": 200000,
            "requiresAPIKey": true
        }
    },
    // Keep Claude Code visible but out of the way
    "claudeCode.preferredLocation": "panel",

    // --------------------------------------------------------
    // ⚡ REMOTE STABILITY
    // --------------------------------------------------------
    "remote.SSH.remotePlatform": {
        "half_1gpu": "linux",
        "127.0.0.1": "linux"
    },
    "security.workspace.trust.untrustedFiles": "open"
}
