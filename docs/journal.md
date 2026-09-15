# Experiment journal

One entry per run, newest last. The run record (`runs/<run_id>/run.json`) is the source of
truth; this journal is the readable narrative that links runs into a tuning history.
Record every attempt, including failed and reverted ones. See [protocol.md](protocol.md) §6.

## Workflow

```bash
run=$(lio-bench run init --method fast_lio2 --sequence exp14 --config <resolved.yaml> \
        --hypothesis "..." --change "..." --parent <run_id> --playback-rate 0.5)
# ... run the method, export its trajectory as TUM ...
lio-bench eval exp14 <trajectory.tum> --frame imu --run-dir "$run"
lio-bench run close "$run" --interpretation "..." --decision keep|revert|investigate
lio-bench log "$run"          # optional: mirror to W&B (offline unless WANDB_MODE=online)
```

## Entry template

```markdown
### <run_id>
- **Method / sequence / split:**
- **Parent:** <run_id or "none (baseline)">
- **Hypothesis:**
- **Change:** <exact parameter or code change; one parameter family at a time>
- **Config hash:**
- **Result:** status, coverage, ATE RMSE / p95, RPE 1 s / 10 s, runtime
- **Interpretation:**
- **Decision:** keep | revert | investigate
```

## Entries

_None yet: no method has been run._
