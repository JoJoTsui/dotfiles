# 04. Preserve the working proxy profile

**What to build:** Stage and validate a proxy refresh so a failure preserves the last working profile and a retry can publish a valid replacement.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] Refresh publishes a valid replacement only after staging and validation. A failed fetch, conversion, or validation preserves the active profile.
- [ ] A valid retry publishes the replacement through the normal deployment command.
- [ ] The temporary deployment process and device proxy retain their existing ownership and lifecycle.
- [ ] Verify failed refresh and successful retry using the existing deployment seam.
