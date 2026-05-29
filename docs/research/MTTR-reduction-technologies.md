# Key AI/ML (AIOps) Technologies for Reducing MTTR in Cloud-Native Systems

*A deep-research report. Scope: AI/ML-driven technologies, cloud-native / Kubernetes /
microservices environments, emphasis on technology categories and concepts (how each
reduces Mean Time To Repair), tool-agnostic. Audience: AIOps/SRE practitioners.*

*Method: 5 parallel fan-out search angles → source fetch + falsifiable-claim extraction →
adversarial verification (per-claim verdicts, confidence tiers) → synthesis. Generated
2026-05-29.*

---

## TL;DR — the honest headline

1. **The biggest finding is a measurement gap.** Across ~60 fetched sources, **no
   peer-reviewed, independent study quantifies an end-to-end MTTR *reduction* attributable
   to a specific AI technique.** Academia rigorously proves **proxy metrics** — detection
   F1, root-cause top‑k accuracy, alert-aggregation F1, lexical similarity of generated
   text. The headline "AIOps cuts MTTR by 40–83%" numbers come **almost entirely from
   vendor marketing or vendor-commissioned studies** with no published methodology. Treat
   those percentages as directional, not evidentiary.

2. **MTTR decomposes; AI attacks different phases with very different maturity.**
   `MTTR ≈ detect + triage + diagnose + repair`. The evidence is strongest where the
   mechanism is *deterministic* (orchestrator self-healing closes the **repair** gap in
   seconds) and where the academic metric maps cleanly to a phase (anomaly detection →
   **detect**; correlation → **triage**; RCA → **diagnose**). It is weakest exactly where
   the marketing is loudest: autonomous end-to-end remediation.

3. **Diagnosis is the high-leverage, hardest phase.** Automated RCA works well on *simple
   resource faults in small systems* (Avg@5 ≈ 0.97–0.99) but **degrades sharply at scale
   and on network/code faults** (best *average* Avg@5 ≈ 0.46–0.54), with "no universal
   winner," and causal-graph construction can be **thousands of times slower** as the graph
   grows.

4. **Human-in-the-loop is currently mandatory, not optional.** Every rigorous production
   source — Google, Microsoft, Zalando, AWS — gates AI suggestions behind human approval.
   LLM RCA agents hit only **~35% correctness** on held-out production incidents; early
   summarization models **hallucinated up to 40%**.

5. **The strongest *independent counter-signal*:** the 2024 DORA report (>39,000
   respondents) found AI adoption associated with a **7.2% decrease in delivery stability**.
   AI does not automatically improve operational outcomes.

---

## How MTTR decomposes (the lens for the rest of this report)

```
        |<---------------------------- MTTR ---------------------------->|
incident |   DETECT    |   TRIAGE    |       DIAGNOSE        |  REPAIR     | resolved
 starts  | (MTTD)      | (page/route | (root-cause analysis) | (mitigate / |
         | anomaly     |  dedup)     |                       |  remediate) |
         | surfaced    |             |                       |             |
```

| Phase | What eats the time | AI technology category | Evidence strength |
|---|---|---|---|
| **Detect** | Threshold blindness, late alarms | Anomaly detection, predictive/failure analytics | Medium–High (proxy metrics) |
| **Triage** | Alert storms, noise, fatigue | Event correlation, dedup, noise reduction | High (proxy metrics) |
| **Diagnose** | "Needle in a haystack," cascades | Automated RCA, topology/dependency-aware analysis, log/trace intelligence | Medium (strong-but-narrow) |
| **Repair** | Manual runbook toil | Self-healing orchestration, runbook/agentic auto-remediation | High for deterministic; Low for autonomous-AI |
| **Cross-cutting** | Coordination, comms, learning | LLM/GenAI incident copilots, summarization, postmortems | Medium |

---

## 1. Anomaly Detection & Predictive Analytics — the DETECT phase

**Technique.** Replace static thresholds with learned models of "normal": forecasting- and
reconstruction-based time-series models, autoencoders/LSTMs on metrics, sequence models on
logs, and graph/sequence models on traces. Predictive (failure-prediction) variants forecast
faults *before* they occur.

**How it cuts MTTR.** Earlier/more-accurate detection shrinks **MTTD**, which gates total
MTTR — you cannot repair what you have not noticed. Predictive analytics aims at the best
case: the incident is *prevented* (MTTR → 0).

**Evidence (proxy = detection quality, not measured MTTR):**

- **DeepTraLog** (GGNN + Deep SVDD over a unified trace+log graph) — precision **0.93**,
  recall **0.97** on the TrainTicket microservice benchmark, **+0.37 average F1** over prior
  trace-only/log-only methods. *Peer-reviewed, ICSE 2022.* **[S1]** — **High confidence.**
- **Trace-NLP LSTM** treats trace spans as language; **F-score 0.9759** (P 0.9774 / R 0.9760),
  10-fold CV on ~5M sequences from a real distributed app. *Peer-reviewed, J. Cloud Computing
  2022.* **[S2]** — **High** (single proprietary dataset → generalization unproven).
- **DeepLog** (LSTM next-log-key prediction) — the landmark online log-anomaly method
  (HDFS + OpenStack), >3,000 citations; widely cited **F-measure ≈ 0.96 on HDFS**. *Peer-
  reviewed, CCS 2017.* **[S4]** — **High** (method/venue); the exact 0.96 is literature
  consensus.
- **Kubernetes graph anomaly detection** (Neo4j cluster graph + unsupervised normality +
  supervised classifier) — Decision-Tree **F1 0.8864**, sub-millisecond prediction on a live
  cluster. *arXiv preprint 2025.* **[S3]** — **Medium** (preprint, synthetic-fault testbed,
  no MTTR quantified).
- **Predictive/preventive** (e.g., disk-failure prediction over SMART data, 30/60/90-day
  windows). *Vendor blog summarizing external research.* **[S36]** — **Medium**; the only
  thread targeting failure *before* it happens, but accuracy numbers undisclosed.

**Caveat.** Every academic result above is a **detection-accuracy proxy**. The detect→MTTR
link is *mechanistic* (faster detection ⇒ shorter MTTD), not directly measured. Benchmarks
like HDFS/BGL are known-saturated; real-world gains are typically smaller.

---

## 2. Alert / Event Correlation & Noise Reduction — the TRIAGE phase

**Technique.** Compress "alert storms" into a few actionable incidents via temporal + spatial
(topology) correlation, deduplication, suppression of self-resolving alerts, and ML/LLM-based
grouping. **Dependency/topology-graph awareness is the recurring cloud-native technique.**

**How it cuts MTTR.** Collapses the **triage** queue so responders work one root incident
instead of sifting hundreds of correlated symptoms — directly attacks alert fatigue.

**Evidence:**

- **COLA** (correlation mining + LLM aggregation) — F1 **0.908 / 0.930 / 0.901** across three
  production datasets, **+37.3% / 47.1% / 36.1%** over the prior best (iPACK); evaluated on
  ~**500,000 alerts**, 60 services, 14 regions; deployed 4 months. *arXiv 2024.* **[S12]** —
  **High** (does not quantify time saved).
- **DiLink** (Microsoft; fuses incident text with the service dependency graph via Orthogonal
  Procrustes embedding alignment) — incident-linking **F1 0.96**, **+14%** over SOTA. *arXiv,
  Microsoft, 2024.* **[S13]** — **High** for F1; operational impact asserted, not measured.
- **DeepCASE** (LSTM + attention + semi-supervised clustering) — reduced analyst workload by
  **>90%** in deployment. *Peer-reviewed, IEEE S&P 2022.* **[S14]** — **High**, but **SOC
  security** domain (adjacent to, not identical to, K8s observability alerting).
- Practitioner/vendor: PagerDuty claims "up to 98%" noise reduction (a named customer reported
  58%, peaking ~86%); Gartner (via a vendor summary) cites "95%+ in extreme cases." **[S16]** —
  **Low–Medium** (best-case marketing; named-customer figures more credible than aggregates).

**Mechanism finding.** Correlation primarily compresses **triage**, not repair; topology-
graph awareness is what makes it work in microservices (independently echoed by COLA, DiLink,
and vendor "topology correlation").

---

## 3. Automated RCA & Topology/Dependency-Aware Analysis — the DIAGNOSE phase

**Technique.** Localize the originating fault among cascading symptoms using: causal discovery
(PC/GES/Granger/LiNGAM/PCMCI) + ranking (PageRank) over metrics; trace-based suspect-set mining;
graph neural networks over service-dependency graphs; and RL-pruned topology graphs. The core
difficulty is **fault propagation** — a symptom surfaces far from its cause.

**How it cuts MTTR.** Diagnosis is widely held to be the largest *controllable* slice of MTTR;
automated RCA returns a short ranked suspect list instead of a manual hunt.

**Evidence — strong but narrow:**

- **"How Far Are We?" causal-RCA benchmark** — best methods (BARO, NSigma) reach **Avg@5
  0.97–0.99** on *simple resource faults* in *small systems* (Online Boutique ~12 svc, Sock
  Shop ~13–15 svc)… **[S6]** — **High.**
- **…but it does not generalize**: best *average* Avg@5 only **0.46 (CIRCA) / 0.54 (RCD)**;
  "no method stands out in all situations." **[S6]** — **High.** *(This is the single most
  important RCA finding.)*
- **…and it does not scale**: causal-graph construction grew **7× to thousands of times slower**
  from 10→50 nodes; slowest method **6,179.77 s** on a 50-node graph; on Train Ticket (64 svc)
  methods took "minutes to an hour." Slow RCA is useless for live-incident MTTR. **[S6]** —
  **High.**
- **TraceRCA** — top-1 root-cause accuracy **+44.8% to +66.1%** over SOTA unsupervised methods;
  deployed at a large commercial bank. *Peer-reviewed, IEEE/ACM IWQoS 2021.* **[S7]** — **High**
  (accuracy, not measured MTTR).
- **TraceDiag** (Microsoft) — RL learns a dependency-graph **pruning policy** before causal RCA;
  deployed as a critical component in **M365 Exchange** with "considerable reduction in human
  effort." *Peer-reviewed, FSE'23 industry.* **[S8]** — **High** (impact stated qualitatively,
  no MTTR number).
- **RCAEval** — public benchmark of **735 failure cases** (metrics+logs+traces), 15 baselines;
  existing methods show only "moderate" results and struggle with network faults. *arXiv
  2024/25.* **[S9]** — **Medium.**
- **Skeptical counterpoint (Google SRE):** Google deliberately **avoids "magic" systems that
  learn thresholds or auto-detect causality**, reports "limited success with complex dependency
  hierarchies," and favors *simple, fast* monitoring (the four golden signals: latency, traffic,
  errors, saturation) + good post-hoc tooling. **[S11]** — **High** (authoritative; ~2016, pre-
  dates recent GNN/LLM RCA).

---

## 4. Log & Trace Intelligence — DETECT + DIAGNOSE

**Technique.** Parse/compress logs (e.g., Drain) and apply BERT/LSTM/LLM sequence models;
model distributed traces as graphs (GNN) or call-sequences (RNN) for per-span latency-outlier
localization.

**How it cuts MTTR.** Flags anomalous logs earlier (detect) and pinpoints the anomalous
service/span in a request path (diagnose), narrowing where to look.

**Evidence:**

- **LogLLM** (BERT semantic embedding → Llama classifier, no traditional parser) — average **F1
  0.959** across four datasets (HDFS 0.997 / BGL 0.916 / Liberty 0.958 / Thunderbird 0.966),
  **+6.6%** over the prior best (NeuralLog). *arXiv 2024/25.* **[S29]** — **High** (benchmark
  saturation caveat applies).
- **Trace intelligence** (TraceGra and similar GNN/sequence models over spans) localize the
  anomalous span/service. *Peer-reviewed + vendor.* — **Medium** (technique well-established;
  specific accuracy not independently re-verified here).

---

## 5. LLM / GenAI Incident Copilots, Summarization & Postmortems — CROSS-CUTTING

**Technique.** LLMs/agents (often ReAct + retrieval/RAG over historical incidents) suggest root
causes and mitigations, summarize incident channels, draft comms/postmortems, and orchestrate
tools via MCP.

**How it cuts MTTR.** Compresses *coordination and cognition* — drafting, summarizing, surfacing
similar past incidents — across diagnosis, communication, and post-incident learning.

**Evidence — the most rigorous independent numbers in this report, but mostly sub-task:**

- **Microsoft, 40,000+ incidents / 1,759 services** — fine-tuned GPT-3.5 improved root-cause
  generation **+45.5%** and mitigation-step generation **+131.3%** in lexical similarity over
  zero-shot; **>70%** of on-call engineers rated suggestions ≥3/5. *Peer-reviewed, ICSE 2023.*
  **[S25]** — **High** (lexical similarity is a proxy; usefulness rating is subjective).
- **Microsoft, LLM RCA agents** — a ReAct GPT-4 agent reached only **~35% correctness** on 500
  held-out production incidents (vs 39% CoT), but cut hallucinations to **<1% / 6%** (vs 26% /
  49% for a retrieval baseline). *Peer-reviewed, FSE 2024.* **[S26]** — **High.** *(Low absolute
  accuracy caps real diagnosis benefit; reasoning agents are more trustworthy.)*
- **Google security** — LLM incident summaries produced **51% faster** at **~10% higher** quality;
  exec comms **53% faster**. Guardrails: skip the LLM under **200 tokens** (else it hallucinates);
  **every summary requires human approval**. *Industry case study.* **[S27]** — **Medium–High**
  (no confidence intervals/model disclosed). *(Summary-time IS a real sub-task reduction.)*
- **Google SRE + Gemini CLI** — agentic LLM orchestrates playbook selection, log/metric analysis,
  patch generation, postmortems over MCP — but **proposes mutations; a human authorizes** ("will
  change… as we build confidence"). *Vendor blog 2026.* **[S28]** — **Medium** (no time metrics).
- **Zalando (2-year production)** — early 3B–12B models **hallucinated up to 40%**; even Claude
  Sonnet 4 retained **~10%** "surface attribution" error; they **rejected a fully-automated
  approach as unfeasible**. Upside: postmortem analysis **days → ~30 s/doc**, surfaced that
  ~80% of one datastore's failures were capacity-driven. *Practitioner blog 2025.* **[S32]** —
  **High** (first-hand, falsifiable failure rates).

---

## 6. Automated / Agentic Remediation & Self-Healing — the REPAIR phase

**Technique.** Two distinct families:
- **Deterministic orchestration (self-healing):** Kubernetes kubelet restarts (`restartPolicy`),
  controller reconciliation to desired replica count, Service endpoint health management,
  HPA/rollback. **No AI required.**
- **Event-driven & agentic automation:** rules/runbook engines (StackStorm, Netflix Winston)
  and AI agents that propose/execute repairs, gated by guardrails.

**How it cuts MTTR.** Directly collapses the **repair** gap — removes humans from routine
toil. This is where the evidence is *deterministically* strongest and *AI-autonomously* weakest.

**Evidence:**

- **Kubernetes self-healing** — kubelet restarts failed containers per `restartPolicy`;
  controllers recreate failed Pods; Services drop unhealthy endpoints. A cached-image pod
  replacement can complete in **~3–8 s**. Repeated crashes are paced by **exponential backoff
  (CrashLoopBackOff, 10s→…→cap 5 min)**. *Authoritative — Kubernetes docs.* **[S17]** —
  **High** (the ~3–8 s figure is a single tutorial measurement → Medium).
- **Google SRE Workbook** — caps toil at **≤50%** of an SRE's time and prescribes progressing to
  *fully automating detection AND remediation*, then fixing root cause in code. *Authoritative.*
  **[S18]** — **High** (principle, not an outcome metric).
- **StackStorm / Netflix Winston** — event→rule→action runbook automation as automated "Tier-1
  support" (Winston: ~22 runbooks, ~15 executions/hr at time of writing). **[S20][S21]** —
  **Medium / Low** (Winston page unreachable; numbers from search summary).
- **AWS DevOps Agent** — agentic AI on Bedrock that uses topology intelligence to generate/test
  hypotheses and **proposes** a mitigation plan (does **not** auto-execute); preview customers
  *self-reported* "up to 75% lower MTTR." *Vendor blog 2026.* **[S19]** — **Medium** for the
  propose-not-execute design; **Low** for the % (vendor preview self-report).

**Safety / guardrails (consolidated — this is the load-bearing engineering, not the % claims):**
- **Least-privilege, read-only by default**; expand scope by category as trust matures (staged
  autonomy), keeping critical paths (payments/auth) approval-gated.
- **Mandatory approval gates** + **GitOps-mediated** change (PRs against Terraform/Helm/Argo/Flux).
- **Blast-radius visibility + confidence-gating** (block low-certainty auto-execution); **rate-
  limiting** (one replica at a time; once per N min; disable during deploys).
- **Crash-loop protection** (exponential backoff) so automation doesn't hammer a broken component.
- **Immutable audit trails**; multi-agent design + "do no harm" + LLM-as-judge to curb
  hallucination. *(Sources: [S22][S23][S19][S17].)*

**Risks.** Automating the *wrong* action can escalate an incident or mask a deeper problem;
LLM hallucination + context saturation ("garbage in, garbage out"); destructive actions
(delete namespace, edit secrets) need hard gates.

---

## Cross-cutting findings (the meta-truths)

1. **Proxy ≠ MTTR.** Peer-reviewed work measures detection F1, RCA top-k, aggregation F1, lexical
   similarity. End-to-end MTTR-% reductions are **vendor/commissioned** (e.g., the recurring
   "~50% MTTR" trace to a **Forrester study commissioned by IBM**; "40–83%" figures lack published
   methodology). **[S31 context, S35]** — Gartner itself flags that *measuring AIOps value* is a
   primary adoption barrier. **[S33]**
2. **Strong-but-narrow RCA.** Excellent on simple faults in small systems; weak at scale and on
   network/code faults; "no universal winner." **[S6]**
3. **Human-in-the-loop is mandatory today.** Google, Microsoft, Zalando, AWS all gate AI output
   behind human approval. Current LLM RCA correctness ≈ 35%. **[S26][S27][S28][S32]**
4. **Deterministic > probabilistic for repair.** The most reliable MTTR win in cloud-native is
   plain orchestrator self-healing — no AI. **[S17]**
5. **Independent counter-evidence exists.** DORA 2024 (>39,000 respondents): AI adoption
   associated with **−1.5% throughput** and **−7.2% delivery stability**; **39%** report little/no
   trust in AI-generated code. Measures AI-for-coding broadly, not incident copilots — but it is
   the strongest independent signal that AI ≠ automatic operational improvement. **[S31]**

---

## Confidence-tiered summary

| Tier | What it covers | Examples |
|---|---|---|
| **High — peer-reviewed, verified** | Detection / RCA / correlation / summarization **proxy** metrics from top venues | DeepTraLog F [S1]; trace-NLP F0.976 [S2]; COLA [S12]; DiLink F0.96 [S13]; DeepCASE >90% [S14]; causal-RCA 0.97–0.99 *and* 0.46–0.54 ceiling [S6]; TraceRCA +44.8–66.1% [S7]; LogLLM F0.959 [S29]; MS ICSE'23 [S25]; MS FSE'24 ~35% [S26]; DORA −7.2% [S31]; K8s self-healing [S17]; Google SRE [S11][S18]; Zalando 40%/10% [S32] |
| **Medium — preprint / single-study / qualitative production** | Recent arXiv, production case studies w/o numbers, vendor *engineering* blogs | K8s graph AD [S3]; RCAEval [S9]; TraceDiag impact [S8]; Google summaries 51/53% [S27]; Gemini CLI [S28]; AWS propose-not-execute [S19] |
| **Low — vendor self-report / commissioned / unverifiable** | The headline MTTR-% marketing | "AIOps cuts MTTR 40–83%" [S35]; PagerDuty "98%" [S16]; AWS "75%" [S19]; Cast AI "40–80%" [S24]; SOC survey wrapper arXiv:2605.08316 (very recent, not independently verified) [S15] |

---

## What this means for an AIOps agent (practical takeaways)

1. **Sequence by ROI and reliability:** deterministic self-healing (repair) → correlation/noise
   reduction (triage) → anomaly detection (detect) → assisted RCA (diagnose) → *guarded* agentic
   remediation. Earliest, most reliable wins are triage + deterministic repair.
2. **Topology/dependency graph is the backbone** — it powers correlation, RCA, and blast-radius
   safety alike. Build/ingest the service graph first.
3. **Treat LLM RCA as a copilot, not an oracle** (~35% correctness): retrieve similar past
   incidents, draft hypotheses/summaries, keep a human in the loop, and **prefer reasoning agents
   for lower hallucination**.
4. **Engineer the guardrails before the autonomy:** least-privilege, approval gates, GitOps,
   confidence-gating, rate limits, crash-loop backoff, immutable audit.
5. **Measure your own MTTR** (and its sub-phases) — do not import vendor percentages. The whole
   field's credibility gap is the absence of measured MTTR; instrument detect/triage/diagnose/
   repair so you can prove (or disprove) impact locally.

---

## Sources

- **[S1]** DeepTraLog — ICSE 2022. https://dl.acm.org/doi/10.1145/3510003.3510180
- **[S2]** Kohyarnejadfard et al., trace-NLP LSTM — J. Cloud Computing 2022. https://pmc.ncbi.nlm.nih.gov/articles/PMC9375740/
- **[S3]** Kubernetes graph anomaly detection — arXiv:2503.14114 (2025). https://arxiv.org/abs/2503.14114
- **[S4]** Du et al., DeepLog — CCS 2017. https://users.cs.utah.edu/~lifeifei/papers/deeplog.pdf
- **[S5]** "A Survey of AIOps in the Era of LLMs" — arXiv:2507.12472 (2025).
- **[S6]** Pham et al., "RCA for Microservices based on Causal Inference: How Far Are We?" — arXiv:2408.13729 (ASE 2024). https://arxiv.org/html/2408.13729v1
- **[S7]** Li et al., TraceRCA — IEEE/ACM IWQoS 2021. https://ieeexplore.ieee.org/document/9521340/
- **[S8]** Microsoft, TraceDiag — FSE'23. https://www.microsoft.com/en-us/research/publication/tracediag-adaptive-interpretable-and-efficient-root-cause-analysis-on-large-scale-microservice-systems/
- **[S9]** Pham et al., RCAEval — arXiv:2412.17015 (2024/25).
- **[S10]** "A Comprehensive Survey on RCA in (Micro)Services" — arXiv:2408.00803 (2024).
- **[S11]** Google SRE Book, "Monitoring Distributed Systems." https://sre.google/sre-book/monitoring-distributed-systems/
- **[S12]** COLA, "Knowledge-aware Alert Aggregation in Large-scale Cloud Systems" — arXiv:2403.06485 (2024).
- **[S13]** Microsoft DiLink, "Dependency Aware Incident Linking" — arXiv:2403.18639 (2024).
- **[S14]** van Ede et al., DeepCASE — IEEE S&P 2022 (security domain).
- **[S15]** "AI-Driven Security Alert Screening… A Comprehensive Survey" — arXiv:2605.08316 (2026, very recent / not independently verified).
- **[S16]** PagerDuty Event Intelligence (vendor). https://www.pagerduty.com/platform/aiops/event-intelligence/
- **[S17]** Kubernetes self-healing docs. https://kubernetes.io/docs/concepts/architecture/self-healing/
- **[S18]** Google SRE Workbook, "Eliminating Toil." https://sre.google/workbook/eliminating-toil/
- **[S19]** AWS DevOps Agent — AWS DevOps Blog (2026). https://aws.amazon.com/blogs/devops/leverage-agentic-ai-for-autonomous-incident-response-with-aws-devops-agent/
- **[S20]** Netflix Winston — Netflix TechBlog (2016).
- **[S21]** StackStorm. https://github.com/StackStorm/st2
- **[S22]** Komodor, "Architecting Agentic AI for SRE" (vendor, 2026).
- **[S23]** RubixKube guardrails (vendor docs). https://docs.rubixkube.ai/concepts/guardrails
- **[S24]** Cast AI, "Agentic Operations" (vendor, 2026).
- **[S25]** Microsoft, "Recommending Root-Cause and Mitigation Steps… using LLMs" — arXiv:2301.03797 (ICSE 2023).
- **[S26]** Microsoft, "Exploring LLM-based Agents for Root Cause Analysis" — arXiv:2403.04123 (FSE 2024).
- **[S27]** Google security LLM incident summaries (via ZenML LLMOps DB). https://www.zenml.io/llmops-database/optimizing-security-incident-response-with-llms-at-google
- **[S28]** Google Cloud, "How Google SREs use Gemini CLI to solve real-world outages" (2026).
- **[S29]** LogLLM — arXiv:2411.08561 (2024/25).
- **[S30]** "A Survey of AIOps for Failure Management in the Era of LLMs" — arXiv:2406.11213.
- **[S31]** DORA 2024 State of DevOps. https://dora.dev/research/2024/dora-report/
- **[S32]** Zalando Engineering, "Dead Ends or Data Goldmines: AI-Powered Postmortem Analysis" (2025).
- **[S33]** Gartner, Market Guide for AIOps Platforms (via IBM/BMC summaries).
- **[S36]** Backblaze, ML for drive-failure prediction. https://www.backblaze.com/blog/using-machine-learning-to-predict-hard-drive-failures/

---

### Verification notes / limitations of this report
- Verification was performed by one independent automated verifier (academic-accuracy lens, in
  flight) plus a domain-expert adversarial reconciliation pass; a third verifier hit a transient
  session limit. No claim required killing (2/3-refute rule); several were **downgraded** to
  reflect proxy-vs-MTTR and vendor provenance.
- Several primary PDFs (TraceRCA, RCAEval, some surveys) returned binary/paywall/403 on fetch;
  their numbers were corroborated via mirrors/indexes and are flagged where on-source verification
  failed.
- arXiv:2605.08316 (SOC alert survey) is dated May 2026 and could not be independently verified;
  its load-bearing primary result (DeepCASE, S&P 2022) is separately real, so the report leans on
  DeepCASE directly.
