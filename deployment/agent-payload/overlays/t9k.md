## T9K remote jobs

Before preparing, submitting, monitoring, or diagnosing a T9K job, read
`~/.local/share/dotfiles/t9k-automation/README.md`. For every job, check the
environment in the worker and link only missing prerequisites when needed.
Use shared A40 or A100 GPUs for GPU workloads, and collect GPU utilization
while the work is running. Run the server-side dry-run before submitting and
verify the terminal job status and requested PVC artifacts.
