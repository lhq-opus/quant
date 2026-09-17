# Reading Guide: From Agent Adoption to End-to-End Delivery

I prepared [From Agent Adoption to End-to-End Delivery: Decisions and Lessons from miHoYo](report.md) for leadership at my current company. It draws on my agent development work and observations at miHoYo, with earlier ByteDance experience as comparative background.

[Chinese reading guide](README.zh-CN.md) · [Chinese report](report.zh-CN.md)

The report is a first-person working draft. Its core miHoYo account covers November 2025 through July 2026, with an update on Anuttacon in approximately August–September 2026. It explains harness engineering through Project S, MCP rework, personal memory, and OpenCode verification, and examines why useful single-task results have not yet established reliable delivery of the full data workflow. The periods overlap; early workflow ambitions and later infrastructure work are kept distinct.

Seven chronological case studies each examine **decisions and actions, possible reasons, and key results**:

1. November–December 2025: the limited starting point and shared-platform discussion, with context on early recruitment for runtime development.
2. After the January 2026 OpenClaw surge: Echo's broad adoption.
3. The months after Echo: the February–April individual-productivity priority, framework-and-skills expansion, server-side project halt, and cost-incident review.
4. March–April: MCP, permissions, disappointing progress, and departmental OpenClaw discontinuation.
5. April initiative: Project S's harness and data flywheel, architecture and rollout gaps, and my FDE work adapting data engineering. Actual changes included memory recovery, data-quality scripts run through a subagent stop hook, the main agent replanning after failed checks, and workflow and model adjustments. Business teams defined and revised acceptance criteria; I provided infrastructure to make models follow them as reliably as possible. Data-return cycles also constrained iteration. The dates of my roughly two-month involvement remain open.
6. May–July: harness work and infrastructure rework, with renewed agent project activity and B2B/FDE needs; the OpenCode-based delivery and verification framework and the personal memory system I drove. Specific project restart and staffing dates remain open.
7. Approximately August–September: Anuttacon recognizes a need for FDE support while promoting its own models to investor-backed companies. Its internal draft principles are compared with the miHoYo cases. Earlier public products, model research, and the AnuNeko shutdown supply context; this is not presented as a pivot into FDE services.

The report separates my experience and judgments, internal draft conclusions, public evidence, and working analysis pending my review. It distinguishes a memory retrieval pipeline from feedback used to train models. Decision options name the case they address and the result needed to evaluate them. Unverified recent recruitment and customer activity remain attributed to my account.

The English and Chinese versions carry the same structure, facts, dates, amounts, reasoning, evidence status, and uncertainties. Both are reviewed together and published in the same commit. The Markdown is prepared for transfer to Confluence; publication to this repository does not publish a Confluence page.
