# Agent resource budget

Agents run builds, test matrices, and parallel jobs. Inside Docker or Kubernetes
the visible CPU count is the host's, while the cgroup quota is what the task may
use. Measure first, then cap parallelism and memory.

## Detect the budget

```sh
#!/bin/sh
set -eu
ncpu=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
if [ -r /sys/fs/cgroup/cpu.max ]; then
    set -- $(cat /sys/fs/cgroup/cpu.max)
    quota=$1; period=$2
elif [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
    quota=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
    period=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)
    [ "$quota" -le 0 ] 2>/dev/null && quota=max
else
    quota=max; period=0
fi
if [ "$quota" = max ] || [ "${quota:-0}" -le 0 ] 2>/dev/null; then
    cpus=$ncpu
else
    cpus=$((quota / period)); [ "$cpus" -lt 1 ] && cpus=1
    [ "$cpus" -gt "$ncpu" ] && cpus=$ncpu
fi
if [ -r /sys/fs/cgroup/memory.max ]; then
    mem=$(cat /sys/fs/cgroup/memory.max)
elif [ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
    mem=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)
else
    mem=$(awk '/MemAvailable/{print $2*1024}' /proc/meminfo 2>/dev/null || echo unknown)
fi
case "$mem" in
    max|unknown) ;;
    *) [ "$mem" -ge 1152921504606846976 ] 2>/dev/null && mem=unlimited ;;
esac
echo "host_cpus=$ncpu effective_cpus=$cpus memory_limit_bytes=$mem"
```

Example from this workstation (Docker, cgroup v1):

```text
host_cpus=64 effective_cpus=46 memory_limit_bytes=83751862272
```

`nproc` shows 64, the quota allows 46, and the memory ceiling is about 78 GiB.
`MemAvailable` on this host describes the machine, not the container, so prefer
the cgroup value.

## Signals and checks

- Container: `/.dockerenv`, `/run/.containerenv`, `KUBERNETES_SERVICE_HOST`, or
  `docker|kubepods|containerd` in `/proc/1/cgroup`. A cgroup-v2 pod may show only
  `0::/`.
- CPU throttling: `/sys/fs/cgroup/cpu.stat` (`nr_throttled`, `throttled_usec`),
  or `/sys/fs/cgroup/cpu/cpu.stat` on v1.
- Contention: `/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io`.
- Disk: `df -h .` and `du -sh` before large builds or downloads.
- Physical macOS: `sysctl -n hw.ncpu`, `sysctl -n hw.memsize`, `vm_stat`.

## Caps

| tool | cap |
| --- | --- |
| make | `MAKEFLAGS=-j$N` |
| cargo | `cargo -j $N` |
| pytest | `pytest -n $N` |
| pixi | `--concurrent-solves N`, `--concurrent-downloads N` on the operation |
| OpenMP / BLAS | `OMP_NUM_THREADS=N`, `OPENBLAS_NUM_THREADS=N`, `MKL_NUM_THREADS=N` |
| Node | `NODE_OPTIONS=--max-old-space-size=<MB>` |

Use `max(1, usable - 1)` for `N`, where `usable` is the smallest of the scheduler
or task grant, the cgroup quota, and `nproc`. Use half the budget when the limit
is unknown. A throttled or OOM-killed run is evidence to reduce, not to retry
unchanged.
