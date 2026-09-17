# Agent Adoption and Delivery: Lessons from miHoYo

**Language:** English | [Chinese version](report.zh-CN.md)

**Status:** Working draft — covers early infrastructure, Echo adoption, subsequent aggressive expansion, and a reported experimentation cost incident; workflow outcomes and analysis remain incomplete.

**Audience:** Leadership at the author's current company.

**Purpose:** Examine agent adoption and delivery at miHoYo, including its data team, and identify lessons for AI decisions at the current company. ByteDance, an earlier employer, provides comparative context.

**Review period:** A one-year retrospective is intended, but exact boundaries remain unconfirmed. The miHoYo account begins with the author's arrival in November 2025, includes Echo's emergence following the OpenClaw surge the author dates to January 2026, and extends through the following two to three months. Echo's dates and the subsequent period's calendar boundaries remain open. The ByteDance comparison covers late 2023 through the end of 2025.

## Executive Summary

When the author joined miHoYo in November 2025, they understood agent projects to be scarce across the company. Their work in the data team was one of those projects. They also recall a privately deployed Dify instance that attracted little attention throughout the period they observed.

By December, the author describes company-level agent infrastructure as limited to an LLM gateway and Dify, alongside a few isolated agent projects. They discussed a general-purpose agent platform running on servers, a skill hub, and knowledge bases with the head of miHoYo's shared team. The aim was to support employees' business workflows and end-to-end work over the following months. This records a planning discussion; approval, resourcing, implementation, and outcomes have not yet been established.

A subsequent turning point was Echo, a general-purpose agent running on employees' clients. Following what the author describes as OpenClaw's surge in popularity in China in January 2026, another project team independently initiated Echo. The author reports broad use across miHoYo, especially among non-R&D staff, regards the project as a company-level success, and attributes adoption to a client UI that substantially reduced the effort needed to get started. Measured task outcomes remain open.

Over the following two to three months, the author characterizes the company's approach as highly aggressive: at least four or five departmental projects adapted OpenClaw, while employees widely moved discrete tasks into agents connected to workplace IM chatbots. The reported company view was that existing frameworks made further development of general-purpose agents unnecessary; employees should write sufficiently comprehensive skills to eventually connect individual tasks into complete workflows spanning everyone's work. This was an ambition; the material so far describes adoption of individual tasks, without establishing that the broader workflow goal was achieved.

The author reports substantial company investment and an employee's multi-agent experiment that incurred RMB 2 million in token costs using Claude Opus 4.6 in one day, with no gateway usage cap or limits on agent numbers and inter-agent message-history volume. The company reportedly treated the incident as a necessary cost of exploring LLMs. The amount, mechanism, and company response are attributed to the author; billing records, experimental outcomes, and subsequent controls have not been supplied.

The author considers miHoYo's start in LLM and agent adoption substantially later than ByteDance's. Their account describes ByteDance moving from LLM applications in customer service and internal engineering productivity in late 2023 toward tools capable of completing certain long tasks by the end of 2025. Detailed outcomes and reasons for the difference remain to be established.

## Context and Scope

The author joined miHoYo's data team in November 2025 and worked on agent development. They previously worked at ByteDance. Their formal title and complete employment dates have not been provided.

The author clarified that the scarcity of agent projects reflected their understanding of miHoYo as a whole, not just their department. This remains a retrospective observation rather than a verified, exhaustive project inventory. The comparison concerns LLM and agent adoption, not the companies' relative strength across all AI research and applications.

Company accounts below come from the author's recollections and clarifications provided on September 17, 2026. Public evidence currently included supports external product timelines, not internal adoption or outcomes. Early LLM use is distinguished from longer-task agents; the account does not imply that all ByteDance applications in 2023 were agents.

## Company Attitudes, Decisions, and Reflection Over Time

| Period | Organization | Reported development |
| --- | --- | --- |
| Late 2023, with expansion afterward | ByteDance | LLM use began in customer service and internal engineering productivity, then gradually spread to other use cases. |
| November 2025 | miHoYo | The author joined the data team to develop agents. In their company-wide understanding, this was one of very few agent projects. |
| December 2025 | miHoYo | Company-level agent infrastructure consisted of an LLM gateway and Dify, a workflow-building platform, alongside a few isolated agent projects. The author discussed a general-purpose platform and supporting infrastructure with the head of the shared team. |
| Observation period not yet specified | miHoYo | An internal, privately deployed Dify instance existed but attracted little attention throughout the period described. |
| By the end of 2025 | ByteDance | Some AI tools could complete certain long tasks end to end, with results the author regarded as very good. |
| Following the author-reported January 2026 OpenClaw surge; Echo dates unconfirmed | miHoYo | Another project team independently initiated Echo, a client-based general-purpose agent. The author reports broad use, particularly among non-R&D staff, and regards it as a major adoption turning point. |
| The following two to three months; exact calendar dates unconfirmed | miHoYo | The author describes aggressive expansion, at least four or five departmental OpenClaw adaptations, widespread migration of discrete tasks into agents and IM chatbots, a company emphasis on existing frameworks and employee-written skills, and substantial investment. A reported one-day RMB 2 million multi-agent experiment was characterized by the company as a necessary exploration cost. |

All entries are attributed to the author. November 2025 is the first reported miHoYo reference point, not an assumed date for its first agent project. The December account confirms that Dify was already available by then; its initial deployment date and the full low-attention observation window remain open.

### December 2025 — Discussion of a shared agent platform

The author spoke with the head of miHoYo's shared team, whom they describe as one seniority level below a company founder. “Shared team” is a provisional translation of the team name; its official English name remains unconfirmed. The seniority description does not establish a specific reporting line.

The discussion concerned how to build the following over the next few months:

- A general-purpose agent platform running on servers.
- Supporting infrastructure, including a skill hub and knowledge bases.
- Support for employees to move the business workflows they were responsible for onto the platform, or to use it to carry out end-to-end work more effectively.

These were discussed capabilities and intended uses. The material does not yet establish agreed action items, project ownership, resources, a committed schedule, or delivery results. It also does not specify whether the new platform would extend, replace, or coexist with Dify. The author's interpretation of the conversation as a partial indication of senior leadership's thinking is recorded below. Subsequent decisions and organizational reflection remain to be documented.

### Following the January 2026 OpenClaw surge — Echo and broader adoption

The author identifies Echo as a major change in employee use of agents. They clarified that it emerged from another project team's self-initiated exploration, independently of the December platform discussion. The two efforts therefore have distinct origins. Whether they later shared infrastructure, and how the server-side proposal progressed, remain unknown.

The reported change concerns an internal team's initiative and broad employee uptake, especially outside R&D. Echo-specific sponsorship and subsequent decisions remain open. Case C03 records the adoption outcome and the author's explanation; the following stage describes a broader change in the company's stance.

### The following two to three months — Aggressive expansion around existing frameworks and skills

The author describes a sharp increase in the company's commitment to LLMs and agents. Departmental teams launched at least four or five projects that wrapped or adapted OpenClaw. Employees began widely transferring scattered, individual tasks into agents and connecting them to workplace instant-messaging chatbots. Project names, departments, the IM product, and whether the count includes Echo remain unspecified (C04).

According to the author, the company's position was that further development of any general-purpose agent was unnecessary because sufficiently capable frameworks were already available. The proposed division of effort was to reuse those frameworks and have employees write comprehensive skills, eventually linking individual pieces of work into complete workflows across employees. The source and formal scope of this position are being clarified. No specific project cancellation, completion of the December platform plan, or successful company-wide workflow integration has been established.

The company reportedly invested substantial resources in this direction. During the period, one employee's multi-agent experiment incurred RMB 2 million in token costs in one day. The author reports that the company ultimately classified this as a necessary cost of exploring LLMs (C05). This is a reported company assessment after the event; the author's own agreement or disagreement has not yet been provided. The precise dates of this stage and the incident remain open.

## Case Studies

### C01 — Agent development in miHoYo's data team

The author identifies their data-team work as one of miHoYo's few agent projects at the time of joining. The business problem, intended users, application type, project start date, decisions, delivery milestones, results, and reflections have not yet been described. Its outcome remains unclassified.

### C02 — Dify deployment and limited attention

**Action reported:** miHoYo had an internal, privately deployed Dify instance. The December 2025 account identifies it as an existing company-level workflow-building platform, alongside an LLM gateway. Its sponsoring team, intended use cases, and relationship to the data-team project or the proposed general-purpose platform are unknown.

**Observation reported:** The author says it attracted little attention throughout the period they observed. That period and the meaning of attention — for example, awareness or actual use — need clarification. No usage, retention, delivered-application, or business-outcome measures have been supplied.

**Assessment:** This observation alone is insufficient to classify the deployment as a failed project or explain its reception. Neither a company assessment nor a specific explanation from the author has yet been provided.

### C03 — Echo: a client-based general-purpose agent with broad uptake

**Background and origin:** The author places Echo's emergence after OpenClaw became highly popular in China in January 2026. Another project team initiated the exploration independently. Echo's start date, initial launch, and wider rollout dates have not been supplied, so the January reference does not establish a January launch.

**Product and action reported:** Echo was a general-purpose agent running on users' clients. The author compares its product form to Kimi Claw and, retrospectively, to the ChatGPT client available when giving this account. These are broad product analogies; Echo's implementation and technical dependencies remain unspecified. Running on a client does not establish that model inference was entirely local.

**Observed outcome and classification:** The author reports widespread use within miHoYo, especially among non-R&D staff, and considers Echo very successful at the company level. The case is recorded as an adoption success in the author's assessment. User counts, adoption rates, retention, concrete tasks, and productivity or business results have not yet been provided.

**Author's explanation:** The client UI substantially lowered the effort required to get started, which the author identifies as a reason for the broad uptake. This is their explanation of the observed outcome; comparative onboarding measurements or evidence isolating the UI's effect have not been supplied.

**Remaining gaps:** The team's identity, specific user workflows, distribution and support, Echo-specific subsequent company decisions, and connections to shared infrastructure remain open. The December proposal's subsequent status is a separate unanswered question.

### C04 — Departmental OpenClaw adaptations and tasks delivered through IM chatbots

**Context and action reported:** In the two to three months following the Echo turning point, at least four or five departmental projects wrapped or adapted OpenClaw. Employees widely moved discrete tasks into agents and connected them to workplace IM chatbots. The author describes substantial company investment, without specifying a total budget.

**Company direction as reported:** Existing agent frameworks were considered sufficient, making further general-purpose agent development unnecessary. Employees were expected to produce comprehensive skills so that separate tasks could eventually be connected into complete workflows spanning employees' work.

**Result and limits:** The account establishes reported expansion of projects and individual-task adoption. The broader workflow objective remains an intended outcome. Skill quality, reuse across teams, concrete task results, operating costs, and the results of connecting tasks have not been supplied. The projects' individual outcomes remain unclassified; the count alone does not establish either productive reuse or wasteful duplication.

### C05 — A reported RMB 2 million day of multi-agent experimentation

**Experiment and reported cost:** During this expansion period, one employee explored multi-agent collaboration using Claude Opus 4.6. The author reports RMB 2 million in token costs within one day. This is a monetary amount, not a token count; its billing or accounting basis has not yet been specified.

**Author's explanation:** The company LLM gateway had no usage cap, and the experiment imposed no limits on the number of agents or the volume of historical messages passed between them. The author attributes the high consumption to these missing limits. Logs and an allocation of cost among these factors have not been supplied.

**Company assessment as reported:** The company ultimately regarded the incident as a necessary cost of exploring LLMs. The source of that characterization is being clarified. It records the reported response after the incident; prior budget authorization and any later changes to controls remain unknown.

**Outcome and evidence:** This is recorded as a cost incident during experimentation. The task attempted, technical result, learning obtained, and business value remain unspecified, so the experiment's overall success or failure is not yet classified. The incident and amount are author-reported. Anthropic's [Opus 4.6 release announcement](https://www.anthropic.com/news/claude-opus-4-6), dated February 5, 2026, supplies model timeline context only.

ByteDance currently provides comparative background. Its individual customer-service, engineering-productivity, and long-task tools remain to be identified before developing full cases.

## Author's Perspective

The author judges miHoYo to have started substantially later in LLM and agent adoption than leading internet companies, particularly ByteDance. This is a personal comparative judgment, not a comprehensive industry ranking or a quantified maturity assessment.

Given the shared-team leader's seniority, the author considers the December discussion partly representative of senior leadership's attitudes and plans for agents at that time. This provides a leadership-related perspective, without establishing a formal company-wide mandate or agreement among all senior leaders.

The author regards Echo as a major turning point and a company-level success. Their explanation emphasizes how the client UI lowered the barrier to use, especially for non-R&D employees. This personal assessment is distinct from a documented company evaluation or a measured causal finding.

The author characterizes the following two to three months as a period of highly aggressive company adoption and substantial spending. The view that general-purpose agent development was unnecessary, and the interpretation of the cost incident as necessary exploration, are presented as company views in their account. The author's personal support, reservations, and later reflections on these positions remain to be documented.

The author recalls regarding Claude Sonnet 4.5 as the strongest model when they joined. Anthropic's announcement confirms its release on September 29, 2025, before that joining month. The release date supports the timing; the assessment of model quality remains the author's. See [Anthropic's release announcement](https://www.anthropic.com/news/claude-sonnet-4-5).

Their favorable assessment of ByteDance's tools concerns certain long tasks. Reliability, task duration, human intervention, and business impact remain unspecified. How the author learned about their state by the end of 2025 also remains open; continued employment at ByteDance then is not assumed.

## Lessons Across Cases

The contrast between Dify's limited attention and Echo's reported broad use supports an initial hypothesis for further investigation: the effort required for employees to get started may be an important factor in adoption alongside platform availability. This is editorial analysis informed by the author's UI explanation, rather than a documented company reflection. The products' purposes, audiences, rollout conditions, and observation periods have not been matched; this is insufficient to establish a general advantage for client-based agents over server-side platforms.

The account now traces a sequence from shared-platform discussions, through a separate team's accessible client product, to aggressive departmental reuse of external frameworks and employee-written skills. The subsequent company stance emphasizes where development effort should go. How this affected the December proposal and Echo's roadmap remains open; the chronology alone does not establish that Echo caused every later decision.

**From individual tasks to connected workflows:** C04 distinguishes an observed expansion in task adoption from the intended integration of work across employees. Editorially, the key proposition to test is whether sufficiently comprehensive skills can support reliable handoffs and complete workflows. More projects and more skills alone do not demonstrate that outcome; representative workflow results are still needed.

**Experimentation appetite and cost control:** C05 pairs a reported willingness to absorb a large exploration cost with specific missing usage limits. An editorial implication is to assess the value of experimentation and the means of bounding each experiment separately. The company's acceptance of the event does not establish what learning the spend produced or whether the same result could have been obtained at lower cost.

## Implications for the Current Company

**Provisional option derived from C03:** If the current company wants broader agent use among non-R&D staff, test an accessible general-purpose agent interface on a small set of representative employee tasks. Assess the effort to complete a first useful task, subsequent use, and task quality before deciding how to expand it. This is an editorial recommendation, not an action or conclusion reported from miHoYo; its relevance depends on the current company's needs and constraints.

**Provisional option derived from C04:** If reusing a general-purpose framework and employee-written skills is under consideration, test the complete workflow with representative handoffs between employees. Assess completion quality and needed human intervention before treating a collection of skills as a complete workflow. The cases do not yet support a blanket decision to stop all internal general-purpose agent development.

**Provisional option derived from C05:** For multi-agent experiments, set a budget and gateway usage limits, cap agent numbers and the message history passed between them, and pause or review a run at defined thresholds. Record each experiment's spending, intended learning, and result together. These are proposed responses to the reported incident, not measures miHoYo is known to have implemented; thresholds should follow the current company's resources and objectives.

The broader assessment should distinguish infrastructure availability, application breadth, actual use, completed workflows, and cost relative to results. Echo and the departmental projects currently provide reported evidence of adoption; sustained use and business value still require further material.

## Open Questions and Evidence Gaps

- What are the full review dates and the author's formal role?
- Did the December 2025 platform discussion result in decisions, owners, resources, or a schedule? Which employee workflows were prioritized, and how would the proposed platform, skill hub, and knowledge bases relate to existing systems? What was later delivered?
- What did the data-team agent project aim to achieve, why was it initiated, and what actions and results followed?
- When was Dify deployed, what period does the low-attention observation cover, and what evidence describes its use? Were any explanations or company reflections offered?
- When was Echo started, launched, and widely adopted, and which team built it? What tasks did non-R&D staff complete, what became easier during onboarding, and what evidence describes adoption, continued use, and task outcomes?
- What formal Echo-specific support or decisions followed, and did it connect to shared infrastructure? What reflections did the company and the author develop afterward?
- What were the exact dates of the subsequent two-to-three-month expansion? Which projects formed the reported count, and did it include Echo? What evidence shows skill reuse and workflows completed across employees?
- Who communicated the view that general-purpose agent development was unnecessary, through what channel, and with what scope? Which projects or resource decisions changed as a result?
- When did the RMB 2 million incident occur, what was its task and result, and what records and accounting basis support the figure? Who characterized it as a necessary cost, and were any limits introduced afterward? What did the author think at the time and in retrospect?
- Which ByteDance tools and teams illustrate the applications described? What counted as completing a long task, and how much human intervention was needed?
- What supports the company timelines and comparisons, including the author's knowledge of ByteDance by the end of 2025?
- Which AI decisions and constraints at the current company should the report address?

## Sources and Evidence Notes

| ID | Source | Date | Claims supported and limits |
| --- | --- | --- | --- |
| U01 | Author's retrospective account and follow-up clarification | Provided September 17, 2026 | Joining date, data-team agent work, company-wide perspective on project scarcity, Dify, earlier ByteDance employment and comparative timeline, and personal assessments. The company accounts have not been independently corroborated here. |
| U02 | Author's account of December 2025 infrastructure and a platform discussion | Provided September 17, 2026 | LLM gateway and Dify as the existing company-level agent infrastructure; a few projects; discussion with the shared-team head; described seniority; proposed platform, skill hub, knowledge bases, and employee use cases. The conversation and seniority are author-reported; its significance for leadership is the author's interpretation. Formal approval and execution are unconfirmed. |
| U03 | Author's Echo account and clarification of its project origin | Provided September 17, 2026 | Emergence following the OpenClaw surge the author dates to January 2026; self-initiated exploration by another project team; client-based general-purpose agent; product analogies; broad uptake especially among non-R&D staff. Success and the UI explanation are the author's assessments. Exact Echo dates, quantitative results, technical dependencies, and subsequent formal decisions remain unconfirmed. |
| U04 | Author's account of the expansion after Echo and a multi-agent cost incident | Provided September 17, 2026 | Following two to three months; at least four or five departmental OpenClaw adaptations; widespread individual-task migration and workplace IM chatbot integration; company emphasis on existing frameworks and comprehensive skills; substantial investment; RMB 2 million in one day using Opus 4.6 with reported missing limits; company characterization as necessary exploration cost. These remain author-reported. Statement provenance, dates, billing evidence, workflow and experimental outcomes, and the author's own evaluation of the company positions remain open. |
| S01 | Anthropic, [Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5) | Published September 29, 2025; accessed September 17, 2026 | Confirms release before the joining month. It does not verify either company's internal adoption or independently establish the best model for every task in November 2025. |
| S02 | OpenClaw documentation, [OpenClaw lore](https://docs.openclaw.ai/start/lore) | Publication date not stated; accessed September 17, 2026 | Records adoption of the OpenClaw name on January 30, 2026, following earlier names. This supports naming chronology, not the timing or extent of popularity in China, Echo's dates, or its implementation. |
| S03 | Kimi Help Center, [What Is Kimi Agent? Features and Entry Points](https://www.kimi.com/en/help/agent/agent-overview) | Publication date not stated; accessed September 17, 2026 | Places Kimi Claw's public beta in mid-February 2026. The author's comparison is retained as a product analogy; it does not establish a January Kimi Claw release or a precise Echo launch date. |
| S04 | Anthropic, [Introducing Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6) | Published February 5, 2026; accessed September 17, 2026 | Confirms the model's public release date. Provides timeline context only; it does not corroborate the miHoYo incident, cost, mechanism, or company response. |
