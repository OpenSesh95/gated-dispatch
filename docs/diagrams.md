# Diagrams

Public vocabulary throughout: *change control* = the review-and-approval discipline around every dispatch; *review gate* = the human approval step; *ledger* = the append-only operating record.

## Context diagram

Where gated-dispatch sits: an operator submits work, an external model provider executes it, and every outcome lands in a ledger the operator can audit and publish.

```mermaid
flowchart LR
    OP[Operator] -->|submit prompt + checks| GD[gated-dispatch]
    GD -->|HTTPS: chat completion| MP[Model provider API]
    MP -->|completion + token usage| GD
    GD -->|verified output| OP
    OP -->|approve / reject at the review gate| GD
    GD -->|one row per run, all outcomes| LED[(Cost ledger - JSONL)]
    LED -->|aggregate: cost per ticket, failure log| REC[Ops receipts]
```

## Sequence diagram

One dispatch, end to end — including the three ways it can end without approval. Exactly one ledger row is written on every path.

```mermaid
sequenceDiagram
    actor Operator
    participant CLI as Dispatch CLI
    participant Provider as Model provider
    participant Verify as Verification checks
    participant Gate as Review gate
    participant Ledger as Cost ledger

    Operator->>CLI: prompt, model, required checks
    CLI->>Provider: chat completion request
    alt provider error
        Provider-->>CLI: error / timeout
        CLI->>Ledger: row - status: error
    else completion returned
        Provider-->>CLI: completion + token usage
        CLI->>Verify: run deterministic checks
        alt checks fail
            Verify-->>CLI: failed checks named
            CLI->>Ledger: row - status: rejected-verification
        else checks pass
            Verify-->>CLI: verified
            CLI->>Gate: present output for approval
            Gate->>Operator: approve? [y/N]
            alt approved
                Operator-->>Gate: yes
                CLI->>Ledger: row - status: approved
            else rejected or no answer
                Operator-->>Gate: no / end of input
                CLI->>Ledger: row - status: rejected-gate
            end
        end
    end
```
