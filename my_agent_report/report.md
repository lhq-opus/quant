# Agent Adoption and Delivery: Lessons from My Experience at miHoYo

**Language:** English | [Chinese version](report.zh-CN.md)

**Status:** Working draft for leadership review. Case outcomes and supporting evidence are still being completed; analytical hypotheses and decision options remain drafts for my review.

**Purpose:** I am reviewing my experience with agent adoption at miHoYo, including my work in its data team, to inform AI decisions at our current company. My earlier experience at ByteDance provides comparative context.

**Review period:** The intended scope is a one-year retrospective, with exact boundaries still to be confirmed. The current account starts with my arrival at miHoYo in November 2025, covers Echo's emergence after the OpenClaw surge I recall in January 2026 and the following two to three months, and includes company-level infrastructure development in March–April 2026. Echo's precise dates, the subsequent expansion period's calendar boundaries, and its overlap with the March–April work remain open. The ByteDance comparison covers late 2023 through the end of 2025.

## Executive Summary

I joined miHoYo's data team in November 2025 to work on agent development. To my knowledge, there were very few agent projects across the company, and mine was one of them. The company had privately deployed Dify, but it attracted little attention throughout the period I observed.

In December, company-level agent infrastructure was still limited, in my understanding, to an LLM gateway and Dify, alongside a few isolated projects. I discussed building a general-purpose server-side agent platform, a skill hub, and knowledge bases with the head of miHoYo's shared team. The aim was to support employees' business workflows and end-to-end work over the following months. The discussion's approval, resourcing, implementation, and results remain to be documented.

I see Echo as a major adoption turning point. Following OpenClaw's surge in popularity in China, which I place in January 2026, another project team independently developed a general-purpose agent running on employees' clients. I observed broad use, particularly among non-R&D staff, and consider Echo a company-level success. In my view, its client UI substantially reduced the effort needed to get started.

Over the next two to three months, I saw the company become highly aggressive in its approach to LLMs and agents. At least four or five departmental projects adapted OpenClaw, and employees widely moved discrete tasks into agents connected to workplace IM chatbots. My understanding of the company's position was that existing frameworks made further general-purpose agent development unnecessary: employees should instead write comprehensive skills, ultimately connecting individual tasks into complete workflows spanning everyone's work. The adoption of individual tasks was visible; achievement of that broader workflow objective remains to be established.

The company invested substantial resources. One incident I recall involved an employee's multi-agent experiment using Claude Opus 4.6, which incurred RMB 2 million in token costs in one day. My understanding is that the gateway did not cap this experiment's usage, and the experiment had no limits on agent numbers or inter-agent message-history volume. I participated in the company's review. The company treated the incident as a necessary cost of exploring LLMs while identifying inadequate gateway quota logic, routing problems that resulted in a low KV cache hit rate, and missing infrastructure for multi-agent and agent-to-agent (A2A) collaboration. Supporting records, the accounting basis, experimental results, and subsequent corrective actions remain to be added.

In March–April 2026, I saw rapid development of company-level agent infrastructure, with MCP interfaces designed for nearly all internal systems. I considered the vast majority of these implementations low quality: many quickly wrapped existing service APIs, retaining designs suited to human use but poorly suited to agents. For example, agents reading data had to repeatedly call MCP tools and adjust pagination parameters, consuming substantial context. I also considered the permissions model inadequately designed; which systems personal agents and team agents should be allowed to access remained unresolved throughout the period I observed.

Compared with ByteDance, where I worked earlier, I consider miHoYo's start in LLM and agent adoption substantially later. ByteDance began applying LLMs to customer service and internal engineering productivity in late 2023 and gradually expanded into other areas. By the end of 2025, some tools could complete certain long tasks end to end, with results I regarded as very good. Detailed outcomes and the reasons for the difference still need further examination.

## Context and Scope

This report combines my participation in miHoYo's data-team agent work, the December platform discussion, and the review of the multi-agent cost incident with my broader observations and recollections. My comments on project scarcity concern the company as a whole, as I understood it at the time; they are not an exhaustive project inventory. The comparison focuses on LLM and agent adoption rather than the companies' overall AI capabilities.

My recollections were recorded on September 17, 2026. The internal developments and company positions described here have not been independently corroborated in this report. Public sources establish external product timelines only. My formal role title and complete employment dates remain to be added.

Throughout the report, I distinguish what I participated in, what I observed or understood about the company, and my personal judgments. Early LLM applications are also distinguished from agents that complete longer tasks; the ByteDance account does not imply that every application in 2023 was an agent.

## How the Company's Approach Evolved

| Period | Organization | What I observed or understood |
| --- | --- | --- |
| Late 2023, expanding afterward | ByteDance | LLM use began in customer service and internal engineering productivity, then spread to other use cases. |
| November 2025 | miHoYo | I joined the data team to develop agents. To my knowledge, this was one of very few agent projects across the company. |
| December 2025 | miHoYo | Existing agent infrastructure consisted of an LLM gateway and Dify, alongside a few projects. I discussed a shared agent platform and supporting infrastructure with the head of the shared team. |
| Observation period to be specified | miHoYo | A privately deployed Dify instance was available but attracted little attention throughout the period I observed. |
| By the end of 2025 | ByteDance | Some AI tools could complete certain long tasks end to end, with results I considered very good. |
| After the OpenClaw surge I recall in January 2026; Echo dates to be confirmed | miHoYo | Another team independently initiated Echo. I observed broad adoption, especially among non-R&D staff, and regard this as a major turning point. |
| The following two to three months; exact dates to be confirmed | miHoYo | I saw aggressive expansion, at least four or five departmental OpenClaw adaptations, widespread individual-task adoption through agents and IM chatbots, and substantial spending. The company emphasized existing frameworks and employee-written skills, and treated a one-day RMB 2 million experiment as a necessary exploration cost. |
| March–April 2026 | miHoYo | I observed rapid infrastructure development and MCP designs for nearly all internal systems. I considered the vast majority of implementations low quality; pagination required repeated calls and consumed substantial context, while access permissions for personal and team agents remained unresolved. |
| Review of the cost incident; date to be confirmed | miHoYo | I participated in the company review, which identified inadequate gateway quota logic, routing problems causing a low KV cache hit rate, and missing infrastructure for multi-agent and A2A collaboration. Corrective actions and their results remain to be documented. |

November 2025 is the starting point of my miHoYo account, not the date of its first agent project. Dify was already available by December; its initial deployment date and the full observation period still need to be specified.

### December 2025 — My discussion of a shared agent platform

I spoke with the head of miHoYo's shared team, whose seniority I describe as one level below a company founder. “Shared team” is a provisional translation; the official English name remains to be confirmed. The seniority description does not establish a particular reporting line.

We discussed how to build the following over the next few months:

- A general-purpose agent platform running on servers.
- Supporting infrastructure, including a skill hub and knowledge bases.
- The ability for employees to move their business workflows onto the platform or use it to complete end-to-end work more effectively.

Given this leader's seniority, I considered the discussion partly representative of senior leadership's attitudes and plans. It was a planning conversation. Agreed action items, ownership, resources, schedules, delivery results, and subsequent organizational reflection remain to be documented, as does whether the proposed platform would extend, replace, or coexist with Dify.

### After the January 2026 OpenClaw surge — Echo and broader adoption

Echo came from another project team's self-initiated exploration, independently of the December platform discussion. I regard its broad uptake, especially outside R&D, as a significant change in employees' use of agents.

The two efforts had distinct origins. Their later use of shared infrastructure, the server-side proposal's progress, and Echo-specific sponsorship and decisions remain open. C03 describes Echo's adoption and my explanation for it.

### The following two to three months — Aggressive expansion around frameworks and skills

I observed a sharp increase in the company's commitment to LLMs and agents. At least four or five departmental projects wrapped or adapted OpenClaw. Employees began widely transferring scattered, individual tasks into agents and connecting them to workplace instant-messaging chatbots.

As I understood it, the company's position was that sufficiently capable frameworks were already available, so further development of any general-purpose agent was unnecessary. The emphasis shifted to reusing those frameworks and having employees write comprehensive skills, with the eventual aim of connecting work across employees into complete workflows.

The company invested substantial resources in this direction. During this period, the multi-agent experiment described in C05 incurred RMB 2 million in one day; the company ultimately classified it as a necessary cost of exploring LLMs. I participated in the company review, which identified inadequate gateway quota logic, routing problems that resulted in a low KV cache hit rate, and missing infrastructure for multi-agent and A2A collaboration. These are the company's assessment and reflections. The review date, resulting actions, and my personal evaluation of the response remain to be developed in this draft.

The formal source and scope of the framework-and-skills position still need clarification. Its effect on specific projects, including the December proposal and Echo, and the results of workflow integration remain to be established.

### March–April 2026 — Rapid MCP development and unresolved usability and permissions

I observed a period of rapid company-level infrastructure development. Nearly all internal systems had MCP interfaces designed for them, and many quickly exposed MCP capabilities by wrapping existing service APIs.

In my assessment, the vast majority of those implementations were low quality. Existing designs carried over poorly to agent use: pagination required agents to repeatedly call tools and adjust parameters when reading data, consuming substantial context. Permissions design also remained inadequate, leaving unresolved which systems personal agents and team agents should be able to access. C06 develops these observations.

These are my assessments of the implementation, rather than company review findings. The work's overlap with the broader expansion period and its timing relative to the cost-incident review still need detail; its relationship to the review's corrective actions has not been established.

## Case Studies

### C01 — My agent development work in miHoYo's data team

The agent work I joined was one of the company's few such projects at the time. This case still needs a fuller account of the business problem, intended users, application type, start date, decisions, delivery milestones, results, and my reflections. Its outcome is not yet classified.

### C02 — Dify deployment and limited attention

**What was available:** miHoYo had a privately deployed Dify instance. By December 2025, I understood it to be an existing company-level workflow-building platform alongside the LLM gateway.

**What I observed:** Dify attracted little attention throughout the period I observed. This draft does not yet define that period or distinguish awareness from actual use, and it includes no measures of usage, retention, delivered applications, or business outcomes.

**Assessment pending:** Limited attention alone is insufficient to classify the project as a failure or explain its reception. The sponsoring team, intended use cases, relationship to the data-team project and proposed platform, company evaluation, and my explanation remain to be added.

### C03 — Echo: a client-based general-purpose agent with broad uptake

**Background and product:** I place Echo's emergence after the January 2026 OpenClaw surge in China. Another project team initiated it independently. It was a general-purpose agent running on users' clients. Its product form reminded me of Kimi Claw and, in retrospect, the ChatGPT client available when I recorded this account in September 2026.

These are broad product analogies. Echo's exact start, launch, and rollout dates, implementation, and technical dependencies remain to be specified. The January reference does not establish a January launch, and a client application does not by itself imply entirely local model inference.

**My assessment:** I observed widespread use within miHoYo, especially among non-R&D staff, and consider Echo a very successful adoption initiative at the company level. I attribute much of that uptake to a client UI that substantially lowered the effort needed to get started. This is my interpretation of the outcome; the draft does not include comparative onboarding measurements or evidence isolating the UI's effect.

**Evidence to add:** User counts, adoption rates, retention, concrete workflows, productivity and business results, the team's identity, distribution and support, subsequent decisions, and links to shared infrastructure. The December platform proposal's subsequent status remains a separate question.

### C04 — Departmental OpenClaw adaptations and IM-based tasks

**What I observed:** In the two to three months after the Echo turning point, at least four or five departmental projects wrapped or adapted OpenClaw. Employees widely moved discrete tasks into agents and connected them to workplace IM chatbots. I saw substantial company investment, although this draft does not include a total budget.

**Company direction as I understood it:** Existing frameworks were considered sufficient. Employees were expected to write comprehensive skills so that separate tasks could eventually become complete workflows spanning their work, without further general-purpose agent development.

**Results so far:** My account describes project expansion and individual-task adoption. The larger workflow objective remains an intended outcome. Project names, departments, the IM product, whether the count includes Echo, skill quality, cross-team reuse, task results, operating costs, and workflow integration results remain to be added. The individual projects' outcomes are unclassified; their number alone does not establish either useful reuse or wasteful duplication.

### C05 — A multi-agent experiment with a reported RMB 2 million daily cost

**The incident as I understand it:** During the expansion period, an employee explored multi-agent collaboration using Claude Opus 4.6 and incurred RMB 2 million in token costs within one day. The amount is a monetary cost; its billing and accounting basis still needs to be established.

**My understanding of the consumption controls:** The company LLM gateway did not cap usage for this experiment. The experiment also lacked limits on agent numbers and the volume of historical messages passed between agents. I associate the high consumption with these missing limits. The draft does not yet include logs or a breakdown of each factor's cost contribution.

**Company review I participated in:** I took part in the company's review of this incident. The company ultimately regarded the expense as a necessary cost of exploring LLMs. Its reflections included:

- Inadequate LLM gateway quota logic.
- Problems with gateway routing logic that resulted in a low KV cache hit rate.
- Missing infrastructure to support multi-agent and A2A collaboration.

These are company findings from the review I attended. The draft does not yet include review records, logs, cache hit-rate measurements, or a cost breakdown to independently assess them. The specific infrastructure gaps and any corrective actions, owners, implementation dates, and results still need detail.

**Assessment pending:** The experiment's task, technical outcome, and business value remain unspecified. The review identified infrastructure problems, but those findings alone do not establish the experiment's overall success or failure. Prior budget authorization also remains to be documented. The event, amount, and review findings rest on my recollection. Anthropic's [Opus 4.6 release announcement](https://www.anthropic.com/news/claude-opus-4-6), dated February 5, 2026, provides model timeline context only.

### C06 — Broad MCP development with usability and permissions gaps

**What I observed:** In March–April 2026, company-level agent infrastructure developed rapidly. Nearly all internal systems had MCP interfaces designed for them. Many implementations were wrappers around existing service APIs, created to expose MCP capabilities quickly. The inventory and the extent of production deployment and actual use remain to be documented.

**My assessment of interface quality:** I considered the vast majority of these implementations low quality. In my view, directly wrapping existing APIs carried over designs suited to human use but poorly suited to agents. When reading data through paginated interfaces, agents had to repeatedly call MCP tools and adjust pagination parameters, consuming substantial context. This is the concrete burden behind my pagination example. The specific systems, tasks, data volumes, call counts, and context consumption have not yet been documented; my assessment concerns the implementations I encountered.

**Unresolved permissions:** I considered the permissions model inadequately designed. The question of which internal systems personal agents and team agents should be allowed to access remained unresolved throughout the period I observed. The meaning of each agent category, concrete permissions questions, and the observation's end date remain to be specified.

**Results and reflection:** My account records broad MCP development alongside context overhead and unresolved access design. Task completion rates, business impact, company decisions on quality and permissions, and subsequent improvements remain to be added. These concerns are my observations and judgments, distinct from the company findings in C05.

ByteDance remains comparative background. Its individual customer-service, engineering-productivity, and long-task tools still need to be identified before developing full cases.

## My Observations and Judgments

I consider miHoYo's start in LLM and agent adoption substantially later than that of leading internet companies, particularly ByteDance. This is my comparative judgment based on the experience described here, rather than an industry ranking or a quantified maturity assessment.

I regarded the December discussion as partly representative of senior leadership's thinking because of the shared-team leader's seniority. That interpretation does not establish a formal company-wide mandate or agreement among all senior leaders.

I consider Echo a major turning point and a company-level adoption success. My explanation centers on how its client UI lowered the barrier to use, particularly for non-R&D employees. This remains my assessment, rather than a documented company evaluation or a measured causal finding.

I describe the following two to three months as a period of highly aggressive adoption and substantial spending. The views that general-purpose agent development was unnecessary and that the cost incident was a necessary exploration expense were company positions as I understood them. I participated in the incident review; the quota, routing, cache, and collaboration-infrastructure findings above record the company's reflections. My own support, reservations, and later reflections on those positions still need to be developed.

My assessment of the March–April MCP work is that broad coverage coexisted with poor interface quality and unresolved permissions design. I linked the usability problems to directly wrapping existing service APIs; repeated pagination calls consumed substantial context during data retrieval. These are my observations and judgments, not a recorded company consensus.

When I joined miHoYo, I regarded Claude Sonnet 4.5 as the strongest model available. [Anthropic's announcement](https://www.anthropic.com/news/claude-sonnet-4-5) confirms its release on September 29, 2025. That supports the timing; the judgment about model quality is mine.

My favorable assessment of ByteDance's tools concerns certain long tasks. Their reliability, task duration, human intervention, and business impact still need detail. The basis for my knowledge of their state by the end of 2025 also needs to be documented; this account does not establish that I remained employed there at that time.

## Working Hypotheses Across Cases

The following hypotheses are draft analysis pending my review and further evidence. They are distinct from the personal judgments above and from miHoYo's own conclusions.

**Access and adoption:** The contrast between limited attention to Dify and broad Echo use raises a hypothesis: the effort needed to get started may matter alongside platform availability. This draws on my explanation of Echo's UI. The products' purposes, audiences, rollout conditions, and observation periods have not been matched, so it does not establish a general advantage for client agents over server-side platforms.

**Where to invest development effort:** The sequence moves from shared-platform discussion, through a separate team's client product, to aggressive reuse of external frameworks and employee-written skills. How the later position affected the December proposal and Echo's roadmap remains open. Timing alone does not establish that Echo caused every subsequent decision.

**From tasks to workflows:** C04 separates adoption of individual tasks from the intended integration of work across employees. The proposition to test is whether comprehensive skills can support reliable handoffs and complete workflows. More projects and skills alone do not establish that result.

**Experimentation and cost:** C05 combines a willingness to absorb a large exploration cost with company reflection on quota logic, routing and cache efficiency, and collaboration infrastructure. This raises a question to test alongside C04: what supporting infrastructure is still needed when reusing general-purpose frameworks and skills? The review findings, the experiment's value, and the effectiveness of subsequent corrective actions need separate assessment. Identifying deficiencies does not establish that they were corrected or what value the experiment delivered.

**MCP coverage and usable access:** C06 suggests assessing integration coverage separately from an agent's ability to complete a task within a reasonable context budget and with clearly defined access permissions. Alongside C04's emphasis on skills, it raises a question about whether the available tools and permissions support complete workflows. The breadth of MCP development alone does not answer that question.

## Decision Options for Our Current Company

These are provisional options derived from the cases, pending my review and assessment against our company's priorities and constraints. They are not finalized recommendations or a record of measures miHoYo implemented.

- **Broader adoption — C03:** If broader use among non-R&D staff is a priority, test an accessible general-purpose agent interface with a small set of representative tasks. Assess the effort to complete a first useful task, repeat use, and task quality before expanding.
- **Framework and skill reuse — C04:** If this approach is under consideration, test complete workflows with representative handoffs between employees. Assess completion quality and required human intervention before treating a collection of skills as a complete workflow. The current cases do not establish a basis for stopping all internal general-purpose agent development.
- **Experimental consumption and infrastructure — C05:** Set experiment budgets and gateway usage limits; cap agent numbers and the message history passed between them; pause or review runs at defined thresholds. Assess routing and KV cache hit rates, and identify infrastructure needs for multi-agent and A2A collaboration. Record spending, intended learning, actual results, and the effects of corrective actions together. Thresholds and infrastructure priorities should reflect our resources and objectives.

- **MCP quality and permissions — C06:** Evaluate representative agent tasks, including the calls and context needed to retrieve data through paginated interfaces. Define which systems personal and team agents may access, and check those boundaries in the same task evaluations. Use completion quality, context consumption, and access problems to guide interface and permissions improvements.

The assessment should distinguish infrastructure availability, application breadth, actual use, workflow completion, and cost relative to results. The Echo and departmental cases currently support adoption observations; sustained use and business value still need evidence. C06 adds interface usability, context consumption, and access permissions to that assessment.

## Information to Complete Before Finalizing

- My formal role title, complete employment dates, and the full review period.
- Decisions, owners, resources, schedules, priority workflows, integration with existing systems, delivery results, and organizational reflection following the December discussion.
- The data-team project's purpose, rationale, actions, results, and my reflections.
- Dify's deployment date, observation period, usage evidence, and explanations for its limited attention.
- Echo's team, start and rollout dates, non-R&D tasks, onboarding changes, adoption and retention evidence, business results, distribution and support, formal sponsorship, later decisions, infrastructure links, and company and personal reflections.
- Exact dates and project coverage for the subsequent expansion, including whether the count includes Echo; evidence of skill reuse and completed workflows across employees.
- Who communicated the position on general-purpose agent development, through which channel and with what scope, and which projects or resource decisions changed.
- The dates of the RMB 2 million incident and its review; the experiment's task, technical outcome, business value, billing records, accounting basis, and cost breakdown; review records, routing and cache measurements, and the specific multi-agent and A2A infrastructure gaps; prior authorization and corrective actions, owners, timing, and effects; my views at the time and in retrospect.
- The March–April MCP system inventory, design and deployment coverage, actual use, representative tasks and measured pagination overhead, quality criteria, definitions of personal and team agents, specific permissions questions and how long they remained unresolved, responsible teams, company decisions, and subsequent improvements; the timing and relationship to the broader expansion and cost-incident review.
- The ByteDance tools and teams, long-task completion criteria, human intervention, reliability, task duration, and business impact, together with the basis for my knowledge of their state by the end of 2025.
- Supporting evidence for the company timelines and comparisons, and the AI decisions and constraints this report should address at our current company.

## Sources and Evidence Notes

| ID | Source | Date | Support and limitations |
| --- | --- | --- | --- |
| U01 | My recollections of joining miHoYo and my earlier ByteDance experience | Recorded September 17, 2026 | Joining date, data-team work, company-wide understanding of project scarcity, Dify, earlier employment and comparative timeline, and my personal assessments. Internal company developments have not been independently corroborated here. |
| U02 | My recollection of December 2025 infrastructure and the platform discussion | Recorded September 17, 2026 | LLM gateway, Dify, few projects, discussion with the shared-team head, the seniority I described, proposed platform, skill hub, knowledge bases, and employee use cases. Leadership significance is my interpretation; formal approval and execution remain unconfirmed. |
| U03 | My observations of Echo and its independent project origin | Recorded September 17, 2026 | Emergence after the OpenClaw surge I place in January 2026; another team's self-initiated exploration; client agent; product analogies; broad use, especially outside R&D. Success and the UI explanation are my judgments. Precise dates, measured results, technical dependencies, and formal Echo-specific decisions remain open. |
| U04 | My recollections of expansion after Echo and the multi-agent cost incident | Recorded September 17, 2026 | Following two to three months; at least four or five departmental OpenClaw adaptations; individual-task adoption and IM integration; company emphasis on frameworks and skills; substantial investment; RMB 2 million in one day using Opus 4.6, missing limits, and the company's response. The source of the framework-and-skills position, dates, billing evidence, workflow and experiment outcomes, and my personal evaluation of those company positions remain open. U05 adds my participation in the incident review. |
| U05 | My participation in the company incident review and confirmation of the cost amount | Recorded September 17, 2026 | I participated in the review. Company reflections covered inadequate gateway quota logic, routing problems causing a low KV cache hit rate, and missing infrastructure for multi-agent and A2A collaboration. I confirmed the amount as RMB 2 million. Review records and measurements have not been independently examined here; corrective actions and their effects remain to be documented. |
| U06 | My observations of March–April infrastructure development, MCP quality, pagination, and permissions | Recorded September 17, 2026 | Rapid development in March–April 2026; MCP designs for nearly all internal systems; many wrappers around existing service APIs; my assessment that the vast majority were low quality; repeated MCP calls and pagination adjustments consuming substantial context during data retrieval; unresolved system access for personal and team agents. Deployment coverage, measured overhead, task outcomes, specific permissions questions, and their duration remain open. These are my recollections and judgments, not independently verified results or company review findings. |
| S01 | Anthropic, [Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5) | Published September 29, 2025; accessed September 17, 2026 | Confirms release before my joining month. It does not verify internal company adoption or establish the strongest model across all tasks in November 2025. |
| S02 | OpenClaw documentation, [OpenClaw lore](https://docs.openclaw.ai/start/lore) | Publication date not stated; accessed September 17, 2026 | Records adoption of the OpenClaw name on January 30, 2026, after earlier names. Supports naming chronology, not the timing or extent of popularity in China or Echo's dates and implementation. |
| S03 | Kimi Help Center, [What Is Kimi Agent? Features and Entry Points](https://www.kimi.com/en/help/agent/agent-overview) | Publication date not stated; accessed September 17, 2026 | Places Kimi Claw's public beta in mid-February 2026. My comparison is a product analogy; it establishes neither a January Kimi Claw release nor Echo's precise launch date. |
| S04 | Anthropic, [Introducing Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6) | Published February 5, 2026; accessed September 17, 2026 | Confirms the public release date. Provides model timeline context only, without corroborating the miHoYo incident, amount, mechanism, or company response. |
