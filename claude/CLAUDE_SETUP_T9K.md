# Claude Code Setup Guide (Remote/Container + Nushell)

## 🎯 The Objective

To run Claude Code (both CLI and VS Code Extension) in a Dockerized environment where:

1. **Storage** is on a network drive (doesn't support file watching).
2. **Resources** are limited (low file watcher count).
3. **Shell** is Nushell (which breaks standard automation scripts).

---

## 🛠 Step 1: Fix the Filesystem (The Symlink Trick)

**Problem:** The network drive (`/t9k/mnt`) crashes when Claude tries to "watch" files (`EINVAL`).
**Solution:** Force Claude to write its cache to `/tmp` (local container storage) while thinking it is writing to your home directory.

Run these commands in your terminal **once per container start**:

```bash
# 1. Setup Global Cache (Fixes startup crash)
# Removes the existing folder if it exists on the network drive
rm -rf ~/.claude
# Creates the physical folder in /tmp
mkdir -p /tmp/claude-global-cache
# Links them
ln -s /tmp/claude-global-cache ~/.claude

# 2. Setup Project Cache (Fixes project loading crash)
# Run this inside your specific project root folder
rm -rf .claude
mkdir -p /tmp/claude-project-$(basename $(pwd))
ln -s /tmp/claude-project-$(basename $(pwd)) .claude

```

---

## 🐚 Step 2: Fix the Shell (The "Guard Clause")

**Problem:** Claude launches a background `bash` process, but your `.bashrc` immediately switches to `nu`, causing a `STDIN is not a TTY` crash.
**Solution:** Modify `.bashrc` to only switch to Nushell if a **real human** is typing.

Open your bash config:

```bash
nano ~/.bashrc

```

Find your existing `exec nu` or `nu` line and **replace** it with this block:

```bash
# --- Smart Nushell Launch ---
# Only launch Nushell if:
# 1. We are in an interactive terminal (-t 0)
# 2. We are NOT running inside a background automation task
if [[ -t 0 && $- == *i* ]]; then
    exec nu
fi

```

*Save and exit (`Ctrl+O` -> `Enter` -> `Ctrl+X`).*

---

## ⚙️ Step 3: Fix the Watcher Limit (Force Polling)

**Problem:** The container has a low limit of file watchers (`ENOSPC`). The VS Code Extension crashes when it hits this limit.
**Solution:** Force the underlying watcher tool (`Chokidar`) to use "Polling" (manual checking) instead of OS events.

1. Open VS Code Settings: **`Ctrl+Shift+P`** -> **"Preferences: Open Remote Settings (JSON)"**
2. Add this configuration block:

```json
{
    "terminal.integrated.env.linux": {
        // Forces the file watcher to use CPU polling instead of OS watchers
        // This bypasses the ENOSPC crash entirely.
        "CHOKIDAR_USEPOLLING": "1",
        
        // Optional: Skips the browser login flow if you have your key
        // "ANTHROPIC_API_KEY": "sk-ant-..." 
    }
}

```

3. **Restart VS Code** completely (`Ctrl+Shift+P` -> "Developer: Reload Window").

---

## 🔄 Step 4: Automate for Container Restarts

Since `/tmp` is wiped every time your Docker container stops, you will lose the cache folders (breaking the symlinks).

Create a script named `init_claude.sh` in your home directory:

```bash
#!/bin/bash
# init_claude.sh

echo "🔧 Setting up Claude Code environment..."

# 1. Re-create Global Cache in /tmp
if [ ! -d "/tmp/claude-global-cache" ]; then
    mkdir -p /tmp/claude-global-cache
    echo "✅ Global cache created in /tmp"
else
    echo "Example: Global cache already exists"
fi

# 2. Re-create Project Cache (Customize this path for your main project)
PROJECT_NAME="rnadnavar" 
if [ ! -d "/tmp/claude-project-${PROJECT_NAME}" ]; then
    mkdir -p "/tmp/claude-project-${PROJECT_NAME}"
    echo "✅ Project cache created for ${PROJECT_NAME}"
fi

echo "🚀 Ready! You can now launch Claude."

```

**Usage:** Whenever you restart your container, just run:

```bash
bash ~/init_claude.sh

```

---

## ✅ Summary Checklist

If Claude stops working, check these three things:

1. [ ] **Symlinks:** Does `ls -ld ~/.claude` point to a valid folder in `/tmp`?
2. [ ] **Environment:** Is `CHOKIDAR_USEPOLLING=1` set? (Type `echo $CHOKIDAR_USEPOLLING` in terminal).
3. [ ] **Shell:** Is `.bashrc` only launching `nu` for interactive sessions?
