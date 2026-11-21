# 05. Upgrade PortableGit with recovery

**What to build:** Upgrade a pinned PortableGit installation that contains vendor links and recover the previous runtime if publication fails.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] Same-pin reapplication reuses its verified installation.
- [ ] A different pin extracts into a confined staging location and passes digest, launcher, and version checks before replacement.
- [ ] Interior vendor links do not prevent upgrading the owned tree. Substituted destination or parent paths remain refused.
- [ ] A failed replacement or retry preserves a usable previous runtime. Exercise same-pin reuse, upgrade, and failure recovery through the Windows installation path.
