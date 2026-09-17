# Agent Adoption and Delivery: Lessons from miHoYo

**Language:** English | [Chinese version](report.zh-CN.md)

**Status:** Early working draft — initial retrospective material recorded; case outcomes and analysis remain incomplete.

**Audience:** Leadership at the author's current company.

**Purpose:** Examine agent adoption and delivery at miHoYo, including its data team, and identify lessons for AI decisions at the current company. ByteDance, an earlier employer, provides comparative context.

**Review period:** A one-year retrospective is intended, but exact boundaries remain unconfirmed. The first miHoYo reference point is the author's arrival in November 2025. The ByteDance comparison covers late 2023 through the end of 2025.

## Executive Summary

When the author joined miHoYo in November 2025, they understood agent projects to be scarce across the company. Their work in the data team was one of those projects. They also recall a privately deployed Dify instance that attracted little attention throughout the period they observed.

By December, the author describes company-level agent infrastructure as limited to an LLM gateway and Dify, alongside a few isolated agent projects. They discussed a general-purpose agent platform running on servers, a skill hub, and knowledge bases with the head of miHoYo's shared team. The aim was to support employees' business workflows and end-to-end work over the following months. This records a planning discussion; approval, resourcing, implementation, and outcomes have not yet been established.

The author considers miHoYo's start in LLM and agent adoption substantially later than ByteDance's. Their account describes ByteDance moving from LLM applications in customer service and internal engineering productivity in late 2023 toward tools capable of completing certain long tasks by the end of 2025. Detailed outcomes and reasons for the difference remain to be established.

## Context and Scope

The author joined miHoYo's data team in November 2025 and worked on agent development. They previously worked at ByteDance. Their formal title and complete employment dates have not been provided.

The author clarified that the scarcity of agent projects reflected their understanding of miHoYo as a whole, not just their department. This remains a retrospective observation rather than a verified, exhaustive project inventory. The comparison concerns LLM and agent adoption, not the companies' relative strength across all AI research and applications.

Company accounts below come from the author's recollections and clarification provided on September 17, 2026. Public evidence currently included verifies the model release timeline only. Early LLM use is distinguished from longer-task agents; the account does not imply that all ByteDance applications in 2023 were agents.

## Company Attitudes, Decisions, and Reflection Over Time

| Period | Organization | Reported development |
| --- | --- | --- |
| Late 2023, with expansion afterward | ByteDance | LLM use began in customer service and internal engineering productivity, then gradually spread to other use cases. |
| November 2025 | miHoYo | The author joined the data team to develop agents. In their company-wide understanding, this was one of very few agent projects. |
| December 2025 | miHoYo | Company-level agent infrastructure consisted of an LLM gateway and Dify, a workflow-building platform, alongside a few isolated agent projects. The author discussed a general-purpose platform and supporting infrastructure with the head of the shared team. |
| Observation period not yet specified | miHoYo | An internal, privately deployed Dify instance existed but attracted little attention throughout the period described. |
| By the end of 2025 | ByteDance | Some AI tools could complete certain long tasks end to end, with results the author regarded as very good. |

All entries are attributed to the author. November 2025 is the first reported miHoYo reference point, not an assumed date for its first agent project. The December account confirms that Dify was already available by then; its initial deployment date and the full low-attention observation window remain open.

### December 2025 — Discussion of a shared agent platform

The author spoke with the head of miHoYo's shared team, whom they describe as one seniority level below a company founder. “Shared team” is a provisional translation of the team name; its official English name remains unconfirmed. The seniority description does not establish a specific reporting line.

The discussion concerned how to build the following over the next few months:

- A general-purpose agent platform running on servers.
- Supporting infrastructure, including a skill hub and knowledge bases.
- Support for employees to move the business workflows they were responsible for onto the platform, or to use it to carry out end-to-end work more effectively.

These were discussed capabilities and intended uses. The material does not yet establish agreed action items, project ownership, resources, a committed schedule, or delivery results. It also does not specify whether the new platform would extend, replace, or coexist with Dify. The author's interpretation of the conversation as a partial indication of senior leadership's thinking is recorded below. Subsequent decisions and organizational reflection remain to be documented.

## Case Studies

### C01 — Agent development in miHoYo's data team

The author identifies their data-team work as one of miHoYo's few agent projects at the time of joining. The business problem, intended users, application type, project start date, decisions, delivery milestones, results, and reflections have not yet been described. Its outcome remains unclassified.

### C02 — Dify deployment and limited attention

**Action reported:** miHoYo had an internal, privately deployed Dify instance. The December 2025 account identifies it as an existing company-level workflow-building platform, alongside an LLM gateway. Its sponsoring team, intended use cases, and relationship to the data-team project or the proposed general-purpose platform are unknown.

**Observation reported:** The author says it attracted little attention throughout the period they observed. That period and the meaning of attention — for example, awareness or actual use — need clarification. No usage, retention, delivered-application, or business-outcome measures have been supplied.

**Assessment:** This observation alone is insufficient to classify the deployment as a failed project or explain its reception. Neither a company assessment nor a specific explanation from the author has yet been provided.

ByteDance currently provides comparative background. Its individual customer-service, engineering-productivity, and long-task tools remain to be identified before developing full cases.

## Author's Perspective

The author judges miHoYo to have started substantially later in LLM and agent adoption than leading internet companies, particularly ByteDance. This is a personal comparative judgment, not a comprehensive industry ranking or a quantified maturity assessment.

Given the shared-team leader's seniority, the author considers the December discussion partly representative of senior leadership's attitudes and plans for agents at that time. This provides a leadership-related perspective, without establishing a formal company-wide mandate or agreement among all senior leaders.

The author recalls regarding Claude Sonnet 4.5 as the strongest model when they joined. Anthropic's announcement confirms its release on September 29, 2025, before that joining month. The release date supports the timing; the assessment of model quality remains the author's. See [Anthropic's release announcement](https://www.anthropic.com/news/claude-sonnet-4-5).

Their favorable assessment of ByteDance's tools concerns certain long tasks. Reliability, task duration, human intervention, and business impact remain unspecified. How the author learned about their state by the end of 2025 also remains open; continued employment at ByteDance then is not assumed.

## Lessons Across Cases

There is not yet enough case evidence to establish recurring patterns or explain the companies' differences. The Dify account raises an editorial question: how did platform availability translate into sustained attention and use? This is a question to investigate, not a conclusion supplied by the author or miHoYo.

The December discussion adds a related question: would a general-purpose platform, skills, and knowledge resources help employees move business workflows onto a shared platform and complete work end to end? The intended direction is now described, but evidence of execution and results is still needed. The existing Dify observation does not by itself explain the motivation for the new platform discussion.

## Implications for the Current Company

Recommendations await detailed cases and the current company's decision context. Further analysis will distinguish infrastructure availability, application breadth, actual use, and task outcomes. This is an editorial framework for assessing subsequent material, not an established finding from the comparison.

## Open Questions and Evidence Gaps

- What are the full review dates and the author's formal role? What happened after the December 2025 platform discussion?
- Did that discussion result in decisions, owners, resources, or a schedule? Which employee workflows were prioritized, and how would the proposed platform, skill hub, and knowledge bases relate to existing systems? What was later delivered?
- What did the data-team agent project aim to achieve, why was it initiated, and what actions and results followed?
- When was Dify deployed, what period does the low-attention observation cover, and what evidence describes its use? Were any explanations or company reflections offered?
- Which ByteDance tools and teams illustrate the applications described? What counted as completing a long task, and how much human intervention was needed?
- What supports the company timelines and comparisons, including the author's knowledge of ByteDance by the end of 2025?
- Which AI decisions and constraints at the current company should the report address?

## Sources and Evidence Notes

| ID | Source | Date | Claims supported and limits |
| --- | --- | --- | --- |
| U01 | Author's retrospective account and follow-up clarification | Provided September 17, 2026 | Joining date, data-team agent work, company-wide perspective on project scarcity, Dify, earlier ByteDance employment and comparative timeline, and personal assessments. The company accounts have not been independently corroborated here. |
| U02 | Author's account of December 2025 infrastructure and a platform discussion | Provided September 17, 2026 | LLM gateway and Dify as the existing company-level agent infrastructure; a few projects; discussion with the shared-team head; described seniority; proposed platform, skill hub, knowledge bases, and employee use cases. The conversation and seniority are author-reported; its significance for leadership is the author's interpretation. Formal approval and execution are unconfirmed. |
| S01 | Anthropic, [Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5) | Published September 29, 2025; accessed September 17, 2026 | Confirms release before the joining month. It does not verify either company's internal adoption or independently establish the best model for every task in November 2025. |
