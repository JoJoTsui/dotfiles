# 08: Pi and OpenCode profile roots

**What to build:** Pi and OpenCode receive a profile root through the `skills`
path already present in their merged settings, instead of the whole shared tree.
The root contains exactly the selected profile plus the generated Herdr skill.
The change must not create duplicate discovery: if either client treats the
setting as additive to a shared root, the test proves there is no duplicate name
and the documented behaviour records the limitation.

**Blocked by:** 04, 06.

**Status:** done

- [x] Pi's merged settings point at a profile root whose contents match the selection.
- [x] OpenCode's merged settings point at a profile root whose contents match the selection.
- [x] No skill name is discovered twice by either client from a managed root.
- [x] The generated Herdr skill appears in both roots.
- [x] A profile change is reflected on the next apply without leftover entries.
- [x] Tests cover both clients, the profile contents, duplicate absence, and reapply.

## Comments

The filtered shared tree is the profile root of both clients. Their merged
settings already register the designated home's `~/.agents/skills`, and that
tree holds the selected profile plus the generated Herdr skill, so no second
copy and no per-client tree was added. The merged path was already absolute
and rendered from the deployment target, so an isolated deployment never falls
back to the host account's home; the tests now pin that for both clients.

The clients differ in what else they scan. Pi resolves the shared tree natively
as the Agent Skills location, so its configured path and the native one name the
same directory and no skill is discovered twice. Pi also scans its own user
root, `~/.pi/agent/skills`, and OpenCode scans its default root,
`~/.config/opencode/skills`, and the project's `.opencode/skills` beside the
configured profile root. The registered profile root wins the name in both
clients, because the merged settings name it: Pi prefers the configured path
over its own root, and OpenCode prefers the configured global root over its
default and project roots. The deployment writes neither root: it reports the
duplicate and preserves the device entry, and
`deployment/agent-payload/skill-roots.tsv` now lists the OpenCode default root
beside Pi's own root so the report covers both clients. The report no longer
claims a warning the client does not give; it states that the client keeps the
first copy and that neither entry is removed.

The limitation is recorded rather than engineered around. The client-settings
merge keeps a device's own skill paths, so an extra configured root can also
repeat a profile name, and a project-local OpenCode skill can shadow a profile
name. Those roots belong to the device, so the deployment reports the roots it
knows and leaves the rest alone.

The pinned clients prove the contract on a disposable home: the Pi SDK resource
loader reports no name collision and the OpenCode 2.2.5 skill API returns each
profile name once, both from the profile root. Those two checks skip without
the pinned clients; the rest run against the simulated home and the hermetic
skill fixture.
