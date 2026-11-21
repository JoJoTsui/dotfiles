# T9K remote jobs

Run `~/.local/bin/t9k-run-job` from the T9K pod with Bash, the host's
`kubectl`, and `python3` for quota checks. It uses the kubeconfig in
`~/.local/share/dotfiles/t9k-automation` for the in-cluster API and reads the
pod's mounted service-account token and CA at runtime. Use
the `aim-xzy` project and keep the token in its mounted file.

## Prepare and submit

1. Identify the absolute script, working directory, data mounts, CPU, memory,
   GPU count, and a new output directory on a PVC. Verify the script and
   working directory are visible under the job's mounts. Treat input files
   as read-only and direct outputs to the agreed directory. Use a short,
   unique DNS-label job name, for example a task prefix and UTC timestamp.
2. For each job, put the environment check at the start of the worker script.
   Follow the [worker environment checks](#worker-environment-and-links)
   below and decide how to capture GPU samples before submission. Use
   `-g 0` for CPU-only work. For GPU work, request the smallest useful number
   of shared GPUs. Prefer the known `a40` queue. Use shared A100s when needed
   if an A100 queue is confirmed for the project. Pass its name with `-q`.
   Use `--standalone-gpu` only when the user requests dedicated GPUs.
3. Run the launcher with `--dry-run` before `--`. It checks the current
   TensorStack Project quota and sends the manifest through server-side
   admission. This does not create a job or reserve quota. Use `--print`
   to inspect the manifest locally. Keep credentials out of command
   arguments, `--env`, and manifests.
4. When the task authorizes submission and the dry-run succeeds, run the
   same command with the same job name and resources, removing
   `--dry-run`. The launcher waits and prints recent logs by default.
   Use `--no-wait` to monitor GPU work from the submitting shell. If creation
   times out or monitoring fails, look up that name before retrying. Escalate
   quota or permission failures before using `--force` or `--skip-quota-check`.

Example dry-run for a CPU task. Substitute the paths and arguments for
the actual script. Launcher flags go before `--`.

```bash
name="task-$(date -u +%Y%m%d-%H%M%S)"
"$HOME/.local/bin/t9k-run-job" -n "$name" -s /t9k/mnt/joey/project/task.sh \
  -w /t9k/mnt/joey/project -g 0 --cpu-limit 2 --mem-limit 4Gi --dry-run \
  -- --out "/t9k/mnt/joey/project/runs/$name"
```

## Worker environment and links

Use the project's check-only setup if it has one. In the worker, check the
effective CPU and memory limits, free space in the output mount, required
input and output paths, and the executable paths and versions the job needs.
Check the worker even if the submitter has already run the same checks.

The reference project's `scripts/setup.sh --check-only --link-dotfiles`
shows the approach. It checks cgroup memory headroom and tool versions,
prints potential links, and leaves the environment untouched. If the check
finds that a link is needed, use the project's documented link step inside
the worker with a trusted, mounted source. Link only missing destinations,
preserve existing files and symlinks, and use the job's private home or
workspace. Use read-only mounts for shared tooling where the job supports
them. Recheck the resolved executable paths and versions before running the
workload, and record the checks in the job log. Stop when a required tool,
mount, or resource is missing.

## Monitor and verify

Use the same kubeconfig and namespace to inspect status, events, and logs.
For direct `kubectl` commands, add the API hostname to `NO_PROXY` as the
launcher does.

```bash
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}${no_proxy:+$no_proxy,}kubernetes.default.svc"
jobdir="$HOME/.local/share/dotfiles/t9k-automation"
k=(kubectl --kubeconfig "$jobdir/kubeconfig-incluster.yaml" -n aim-xzy)
kind=pytorchtrainingjobs.batch.tensorstack.dev
"${k[@]}" get "$kind" "$name" \
  -o jsonpath='{.status.phase}{"\n"}{.status.tasks[*].replicas[*].containers[*].exitCode}{"\n"}'
"${k[@]}" describe "$kind" "$name"
"${k[@]}" get pods -l "tensorstack.dev/owner-name=$name"
"${k[@]}" logs -l "tensorstack.dev/owner-name=$name" -c pytorch --tail=200
```

For each GPU job, verify the visible GPU count and model at worker startup.
Use the framework's device check when the workload depends on CUDA. Sample
utilization and memory while the workload is active, with several samples
during steady-state processing when the job runs long enough. For example,
run this in the worker script or use `kubectl exec` against its running Pod.
For short jobs, collect samples in the worker and retain them with the job
logs or output artifacts.

```bash
nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,memory.used,memory.total \
  --format=csv
```

Record the queue, GPU model and count, and sampled utilization and memory.
On shared GPUs these are device-level readings that may include other jobs.
Use workload throughput or per-process profiler metrics to assess the job's
own performance. If measurements are unavailable, report that explicitly.
For CPU-only jobs record GPU utilization as not applicable.

Inspect the Pod events with `describe pod` for scheduling, PVC, and image-pull
errors. If the service account gets `Forbidden`, use `kubectl auth can-i` with
the same kubeconfig and namespace to identify the missing permission.
Record the job name, phase, and container exit code. Require `Succeeded`,
zero exit codes, and the requested artifacts on the PVC. Check artifact size,
record count, or checksum as appropriate. Keep the job and logs available
for inspection. Delete the job only when the user authorizes cleanup.

## Launcher defaults

The launcher creates a single-worker TensorStack
`batch.tensorstack.dev/v1beta1` `PyTorchTrainingJob` on queue `a40` at priority
0. It uses the T9K Torch 2.5.0 image, requests 500m CPU and 500Mi memory, and
limits them to 20 CPU and 100Gi. Size limits for the workload. The default is
one shared GPU (`nvidia.com/gpu.shared`) with a 16Gi memory-backed `/dev/shm`.
Select the shared-memory size with `--shm`. It counts against Pod memory.
Use `--help` for overrides.

| Default PVC | Mount path |
| --- | --- |
| `ssd-joey` | `/t9k/mnt/joey` |
| `omics-cephfs` | `/t9k/mnt/omics` |
| `scllm-cephfs` | `/t9k/mnt/scllm` |
| `neoantigen` | `/t9k/mnt/WorkSpace` |
| `obs-xuzy` | `/t9k/mnt/hdd` |

For a mount-free inline task, use `--no-default-mounts -w /tmp`. Add a PVC
with `--mount PVC:/path`. Write durable results to a PVC.

References

- [TensorStack PyTorchTrainingJob API](https://t9k.github.io/user-manuals/latest/references/api-reference/pytorchtrainingjob.html)
- [Kubernetes API dry-run](https://kubernetes.io/docs/reference/using-api/api-concepts/#dry-run)
- [Kubernetes service accounts](https://kubernetes.io/docs/concepts/security/service-accounts/)
- [kubectl reference](https://kubernetes.io/docs/reference/generated/kubectl/kubectl-commands/)
- [NVIDIA System Management Interface](https://docs.nvidia.com/deploy/nvidia-smi/)
