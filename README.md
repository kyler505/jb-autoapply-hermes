# jb-autoapply-hermes

Hermes-native auto-apply pipeline for the `jb` Obsidian vault.

This repo is built to use the existing vault at `~/Obsidian/jb` as its source of truth.
It improves the original Cowork workflow by making the pipeline explicit and deterministic:

- queue/filter/rank jobs from the vault
- write review packets into each job note
- compile or select the right resume artifact
- generate a site-aware apply plan with hard review boundaries
- keep the manual submit step separate

## Quick start

```bash
cd ~/jb-autoapply-hermes
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
jb-autoapply doctor
jb-autoapply queue
jb-autoapply prepare --limit 5
jb-autoapply plan --limit 3
```

## Vault source

The default source vault is:

```
~/Obsidian/jb
```

Override with:

```bash
export JB_VAULT=/path/to/jb
```

## Commands

- `doctor` — validate the source vault and runtime prerequisites
- `queue` — filter/rank jobs and write `out/queue.json` + `out/queue.md`
- `prepare` — write `## Application <date>` packets into queued notes
- `plan` — emit site-aware apply plans for the queued jobs

## What this repo does not do

It does not auto-submit applications. The review gate stays manual on purpose.
