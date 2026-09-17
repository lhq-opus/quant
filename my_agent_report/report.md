# Agent Adoption and Delivery: Lessons from My Experience at miHoYo

**Language:** English | [Chinese version](report.zh-CN.md)

**Status:** Working draft for leadership review. Case outcomes and supporting evidence are still being completed; analytical hypotheses and decision options remain drafts for my review.

**Purpose:** I am reviewing my experience with agent adoption at miHoYo, including my work in its data team, to inform AI decisions at our current company. My earlier experience at ByteDance provides comparative context.

**Review period:** The intended scope is a one-year retrospective, with exact boundaries still to be confirmed. The current miHoYo account runs from my arrival in November 2025 through July 2026: early platform discussion, Echo's emergence and subsequent expansion, March–April infrastructure and delivery problems, a founder's April push for Project S, and May–July work on harness engineering and supporting infrastructure. Precise project, rollout, and outcome dates remain open. The ByteDance comparison covers late 2023 through the end of 2025; Anuttacon provides a comparison within the Project S case.

## Executive Summary

I joined miHoYo's data team in November 2025 to work on agent development. To my knowledge, there were very few agent projects across the company, and mine was one of them. The company had privately deployed Dify, but it attracted little attention throughout the period I observed.

In December, company-level agent infrastructure was still limited, in my understanding, to an LLM gateway and Dify, alongside a few isolated projects. I discussed building a general-purpose server-side agent platform, a skill hub, and knowledge bases with the head of miHoYo's shared team. The aim was to support employees' business workflows and end-to-end work over the following months. The discussion's approval, resourcing, implementation, and results remain to be documented.

I see Echo as a major adoption turning point. Following OpenClaw's surge in popularity in China, which I place in January 2026, another project team independently developed a general-purpose agent running on employees' clients. I observed broad use, particularly among non-R&D staff, and consider Echo a company-level success. In my view, its client UI substantially reduced the effort needed to get started.

Over the next two to three months, I saw the company become highly aggressive in its approach to LLMs and agents. At least four or five departmental projects adapted OpenClaw, and employees widely moved discrete tasks into agents connected to workplace IM chatbots. My understanding of the company's position was that existing frameworks made further general-purpose agent development unnecessary: employees should instead write comprehensive skills, ultimately connecting individual tasks into complete workflows spanning everyone's work. The adoption of individual tasks was visible; achievement of that broader workflow objective remains to be established.

The company invested substantial resources. One incident I recall involved an employee's multi-agent experiment using Claude Opus 4.6, which incurred RMB 2 million in token costs in one day. My understanding is that the gateway did not cap this experiment's usage, and the experiment had no limits on agent numbers or inter-agent message-history volume. I participated in the company's review. The company treated the incident as a necessary cost of exploring LLMs while identifying inadequate gateway quota logic, routing problems that resulted in a low KV cache hit rate, and missing infrastructure for multi-agent and agent-to-agent (A2A) collaboration. Supporting records, the accounting basis, experimental results, and subsequent corrective actions remain to be added.

In March–April 2026, I saw rapid development of company-level agent infrastructure, with MCP interfaces designed for nearly all internal systems. I considered the vast majority of these implementations low quality: many quickly wrapped existing service APIs, retaining designs suited to human use but poorly suited to agents. For example, agents reading data had to repeatedly call MCP tools and adjust pagination parameters, consuming substantial context. I also considered the permissions model inadequately designed; my account of this stage records unresolved questions about which systems personal and team agents should be allowed to access.

During March–April, I recall a widespread sense that progress on AI projects was falling short of expectations. I understood the company's view to be that anyone could create agents. My assessment is that it overlooked the need to provide company-level infrastructure designed for AI and agent workflows, and I link that gap to the disappointing progress. During this period, nearly all departmental OpenClaw deployments were taken offline and no longer used. The reasons for each discontinuation still need to be documented.

By April 2026, I still saw a highly aggressive approach to agents. A miHoYo founder personally promoted Project S, built around Claude Code and workplace IM, with the aim of moving all workflows of a team or department into it. The design combined team memory visible to all members with an agent holding every member's data permissions. In my account, the initial rollout progressed more smoothly at Anuttacon, the founder's other LLM company, where permissions were simpler. At miHoYo, I saw complex permissions as the largest obstacle and considered the shared-memory model and concentration of all work entry points in IM too aggressive. The intended rollout did not progress; its final scope and status still need clarification.

From May through July 2026, I observed a less aggressive company-level approach, while employees and departments widely explored harness engineering: what context to provide when using Codex, Claude Code, and pi agent to better constrain agents through long tasks. They also investigated the infrastructure needed for end-to-end delivery involving multiple people or agents. Nearly all previously rushed MCP interfaces were refactored, and knowledge-base retrieval, agent permissions, and memory capabilities were added or developed.

Two departmental projects stood out to me as popular internally. An OpenCode-based framework offered development, deployment, and release from end to end; it initially appealed to non-R&D staff, then gained some acceptance among R&D staff after adding agent end-to-end verification. Its front-end and back-end deployment capabilities allowed engineers to have agents verify the output using browser use or Playwright. I drove the other project, a memory system for personal collaboration across endpoints and agents, allowing memory to move between them. Detailed delivery results and measures of adoption remain to be documented.

Compared with ByteDance, where I worked earlier, I consider miHoYo's start in LLM and agent adoption substantially later. ByteDance began applying LLMs to customer service and internal engineering productivity in late 2023 and gradually expanded into other areas. By the end of 2025, some tools could complete certain long tasks end to end, with results I regarded as very good. Detailed outcomes and the reasons for the difference still need further examination.

## Context and Scope

This report combines my participation in miHoYo's data-team agent work, the December platform discussion, the review of the multi-agent cost incident, and my work to advance a personal agent-memory system with my broader observations and recollections. My comments on project scarcity concern the company as a whole, as I understood it at the time; they are not an exhaustive project inventory. The comparison focuses on LLM and agent adoption rather than the companies' overall AI capabilities.

My recollections were recorded on September 17, 2026. The internal developments and company positions described here have not been independently corroborated in this report. Public sources establish external product timelines and Anuttacon's name and stated research focus, without verifying internal rollouts. My formal role title and complete employment dates remain to be added.

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
| March–April 2026, during the same period | miHoYo | I recall a widespread sense that AI project progress was below expectations. The company believed anyone could create agents; I considered company-level AI-native infrastructure neglected. Nearly all departmental OpenClaw deployments were taken offline and no longer used. |
| April 2026 initiative; rollout dates to be confirmed | miHoYo; Anuttacon | A miHoYo founder personally promoted Project S. I recall smoother initial progress at Anuttacon, followed by an unsuccessful attempt to advance the intended rollout at miHoYo. I link this difference to permissions complexity and consider the team memory and IM requirements too aggressive for miHoYo. |
| May–July 2026 | miHoYo | I observed a less aggressive company-level approach alongside widespread departmental harness work. Nearly all rushed MCP interfaces were refactored; retrieval, agent permissions, and memory capabilities were developed. An OpenCode-based delivery framework gained popularity, and I drove a personal memory system spanning endpoints and agents. |
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

### March–April 2026 — Rapid infrastructure expansion and progress below expectations

I observed a period of rapid company-level infrastructure development. Nearly all internal systems had MCP interfaces designed for them, and many quickly exposed MCP capabilities by wrapping existing service APIs.

In my assessment, the vast majority of those implementations were low quality. Existing designs carried over poorly to agent use: pagination required agents to repeatedly call tools and adjust parameters when reading data, consuming substantial context. Permissions design also remained inadequate, leaving unresolved which systems personal agents and team agents should be able to access. C06 develops these observations.

I understood the company to believe that anyone could create agents. My broader assessment is that it overlooked company-level AI-native infrastructure, despite the rapid expansion of MCP coverage. I connect this gap to the widespread sense I recall in March–April that AI projects were not progressing as expected. During this period, nearly all departmental OpenClaw deployments were taken offline and no longer used, as recorded in C04.

The infrastructure assessment and causal explanation are mine; the widespread sentiment is my observation, not a survey result or formal company review. Specific shutdown reasons and decisions remain open. The period's overlap with the broader expansion and its timing relative to the cost-incident review still need detail; its relationship to the review's corrective actions has not been established.

### April 2026 — A founder's push for Project S

I saw the company's aggressive stance continue into April, when a miHoYo founder began personally promoting Project S. The initiative used Claude Code with what I describe as “harness engineering” and integrated workplace IM. Its ambition was to bring all workflows of a team or department into one system, with shared team memory and an agent holding the data permissions of every team member.

In my account, the founder first introduced it at Anuttacon, his other LLM company. I attribute its smoother initial progress there to a startup environment with simpler permissions. At miHoYo, the intended rollout did not progress. I regarded its complex permissions as the largest obstacle and the requirements for memory visible to the entire team and all work entry points in IM as too aggressive. C07 separates the design, the rollout comparison, and my assessment.

The founder's involvement is a concrete leadership action in my account. How Project S related to the earlier framework-and-skills position, Echo, the December platform discussion, or the cost-incident review remains unspecified.

### May–July 2026 — A less aggressive company approach and continued departmental engineering

At the company level, I observed a less aggressive approach than in the preceding months. At the employee and departmental levels, harness engineering became a common focus. In the work I am describing, this meant exploring what context to give Codex, Claude Code, or pi agent so that agents could be better constrained to complete long tasks. Teams also examined what infrastructure was needed to deliver a task end to end when multiple people or agents were involved.

I regard these three months as a period of improving agent infrastructure. Nearly all of the MCP interfaces that had previously been rushed into use were refactored. Knowledge-base retrieval capabilities, an agent permissions system, and agent memory systems were added or developed. C06 records this follow-up to the earlier infrastructure problems; the extent to which individual quality and access issues were resolved still needs evidence.

Departmental projects continued to gain traction. C08 covers the OpenCode-based framework's development-to-release capabilities and changing reception among non-R&D and R&D staff. C09 covers the memory system I drove for personal work across endpoints and agents. The less aggressive company attitude is my observation; formal policy, resource changes, and the reasons for that shift remain to be documented. The relationship between this work and the earlier cost-incident review is also unconfirmed.

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

### C04 — Departmental OpenClaw expansion and subsequent discontinuation

**What I observed:** In the two to three months after the Echo turning point, at least four or five departmental projects wrapped or adapted OpenClaw. Employees widely moved discrete tasks into agents and connected them to workplace IM chatbots. I saw substantial company investment, although this draft does not include a total budget.

**Company direction as I understood it:** Existing frameworks were considered sufficient, and the company believed anyone could create agents. Employees were expected to write comprehensive skills so that separate tasks could eventually become complete workflows spanning their work, without further general-purpose agent development.

**Subsequent outcome:** During March–April 2026, nearly all departmental OpenClaw deployments were taken offline and no longer used. I also recall a widespread sense during this period that progress on AI projects was below expectations. The early expansion and individual-task adoption were followed by widespread discontinuation; the larger objective of complete workflows across employees remains unconfirmed.

**My reflection and remaining evidence:** I attribute the shortfall in progress to a company approach that encouraged everyone to create agents while overlooking shared AI-native infrastructure. This is my explanation of the period, rather than an established cause for every discontinued deployment. Project and deployment names, departments, shutdown dates and decisions, whether Echo was included, and the mapping to the earlier count of at least four or five projects remain to be specified. The IM product, skill quality, cross-team reuse, delivered task results, operating costs, and workflow outcomes also need evidence.

### C05 — A multi-agent experiment with a reported RMB 2 million daily cost

**The incident as I understand it:** During the expansion period, an employee explored multi-agent collaboration using Claude Opus 4.6 and incurred RMB 2 million in token costs within one day. The amount is a monetary cost; its billing and accounting basis still needs to be established.

**My understanding of the consumption controls:** The company LLM gateway did not cap usage for this experiment. The experiment also lacked limits on agent numbers and the volume of historical messages passed between agents. I associate the high consumption with these missing limits. The draft does not yet include logs or a breakdown of each factor's cost contribution.

**Company review I participated in:** I took part in the company's review of this incident. The company ultimately regarded the expense as a necessary cost of exploring LLMs. Its reflections included:

- Inadequate LLM gateway quota logic.
- Problems with gateway routing logic that resulted in a low KV cache hit rate.
- Missing infrastructure to support multi-agent and A2A collaboration.

These are company findings from the review I attended. The draft does not yet include review records, logs, cache hit-rate measurements, or a cost breakdown to independently assess them. The specific infrastructure gaps and any corrective actions, owners, implementation dates, and results still need detail.

**Assessment pending:** The experiment's task, technical outcome, and business value remain unspecified. The review identified infrastructure problems, but those findings alone do not establish the experiment's overall success or failure. Prior budget authorization also remains to be documented. The event, amount, and review findings rest on my recollection. Anthropic's [Opus 4.6 release announcement](https://www.anthropic.com/news/claude-opus-4-6), dated February 5, 2026, provides model timeline context only.

### C06 — MCP and permissions: rapid rollout followed by infrastructure rework

**What I observed:** In March–April 2026, company-level agent infrastructure developed rapidly. Nearly all internal systems had MCP interfaces designed for them. Many implementations were wrappers around existing service APIs, created to expose MCP capabilities quickly. The inventory and the extent of production deployment and actual use remain to be documented.

**My assessment of interface quality:** I considered the vast majority of these implementations low quality. In my view, directly wrapping existing APIs carried over designs suited to human use but poorly suited to agents. When reading data through paginated interfaces, agents had to repeatedly call MCP tools and adjust pagination parameters, consuming substantial context. This is the concrete burden behind my pagination example. The specific systems, tasks, data volumes, call counts, and context consumption have not yet been documented; my assessment concerns the implementations I encountered.

**Permissions gaps in the early rollout:** I considered the permissions model inadequately designed. My March–April account records unresolved questions about which internal systems personal and team agents should be allowed to access. The agent categories, specific access questions, and when individual issues were resolved remain to be specified. C07 provides a case involving access across a team's data and shared memory.

**May–July follow-up:** Nearly all of the MCP interfaces that had been rushed into use were refactored. Knowledge-base retrieval, agent permissions, and agent memory capabilities were also added or developed during these three months. The changes to specific interfaces, the permissions model's coverage, and before-and-after task results have not yet been documented.

**Results and reflection:** I observed broad rollout, usability and access problems, and later infrastructure rework. The rework does not by itself establish that all earlier problems were resolved. Task completion, context consumption, business impact, ownership, and the company's formal assessment still need evidence. My account of this work remains separate from the company review findings in C05; a direct link to that review's corrective actions has not been established.

### C07 — Project S: a founder's initiative constrained by permissions and workflow design

**Initiative and goal:** In April 2026, a miHoYo founder began personally promoting Project S. It was built around Claude Code using what I describe as “harness engineering” and integrated workplace IM. The ultimate goal was to move every person's workflows within a team or department into Project S; this was an ambition, not an established migration result.

**Memory, access, and work entry points:** The design called for team-level agent memory built from work conversations between people and between people and agents, meetings, documents, and related material. Memory derived from members' work was to be visible to the entire team. The agent's access model gave it the data permissions of every team member. Bringing all work entry points into IM was intended to let Project S capture the full context of those workflows. The extent to which these capabilities and permissions were actually deployed at miHoYo remains to be documented.

**Anuttacon comparison:** As I understand it, the founder first promoted the project at Anuttacon, his other LLM company. I describe Anuttacon as a startup with a relatively simple permissions system, which made the rollout smoother. This is my explanation of the difference; completed workflow migrations, adoption measures, and business results have not been provided in this account. Anuttacon's official self-description is recorded in S05; it does not verify Project S or the founder connection.

**miHoYo outcome and my assessment:** The intended rollout did not progress at miHoYo. I considered its intricate permissions system the largest implementation obstacle. I also regarded the project as highly idealistic: building memory from employees' work that would be visible to everyone in the team, and moving all work entry points to IM to capture complete context, were too aggressive for this setting. These are my explanations for the rollout difficulty, rather than a documented company review. The final project status, pilot scope, and whether any parts remained in use still need clarification.

### C08 — An OpenCode-based framework for development, deployment, and verification

**Capabilities and setting:** During May–July, a departmental project built on OpenCode offered an agent framework covering development, deployment, and release end to end. I considered it one of the departmental projects that were popular within the company. The project's name and sponsoring department remain to be added.

**Adoption as I observed it:** Non-R&D colleagues initially liked using it. Later, as it added what I describe as agent end-to-end verification, R&D colleagues also showed some acceptance. This is a change in reception that I associate with the added capability; it is not a quantified measure of R&D-wide adoption or proof that verification was the only factor.

**Verification capability:** The framework provided both front-end and back-end deployment. Engineers could therefore ask an agent to verify the output directly through browser use or Playwright. This describes the available verification path; a concrete run, the checks performed, and its results still need to be documented.

**Evidence to add:** A representative verification task and acceptance criteria, release and adoption dates, projects actually delivered, human involvement, quality and operating costs, and sustained use. The availability of development-to-release capabilities does not establish that every task completed successfully or without human intervention.

### C09 — My project to make personal agent memory portable

**My role and the problem:** I drove a departmental memory-system project during this period. It addressed a person's collaboration across multiple endpoints and multiple agents. I considered it another project that was popular internally.

**What the system enabled:** Agent memory could move from one endpoint to another and from one agent to another. This capability addressed personal continuity across those environments. It is distinct in scope from C07's team-wide shared-memory goal; I have not established a technical or organizational relationship between the two projects.

**Results and evidence to add:** The system supported memory transfer, and I observed a positive reception within the company. The supported endpoints and agents, memory content, transfer mechanism, permissions, representative task, adoption measures, and effects on task completion remain to be documented. Its relationship to the data-team project I joined in C01 also needs clarification.

ByteDance remains comparative background. Its individual customer-service, engineering-productivity, and long-task tools still need to be identified before developing full cases.

## My Observations and Judgments

I consider miHoYo's start in LLM and agent adoption substantially later than that of leading internet companies, particularly ByteDance. This is my comparative judgment based on the experience described here, rather than an industry ranking or a quantified maturity assessment.

I regarded the December discussion as partly representative of senior leadership's thinking because of the shared-team leader's seniority. That interpretation does not establish a formal company-wide mandate or agreement among all senior leaders.

I consider Echo a major turning point and a company-level adoption success. My explanation centers on how its client UI lowered the barrier to use, particularly for non-R&D employees. This remains my assessment, rather than a documented company evaluation or a measured causal finding.

I describe the following two to three months as a period of highly aggressive adoption and substantial spending. The views that general-purpose agent development was unnecessary and that the cost incident was a necessary exploration expense were company positions as I understood them. I participated in the incident review; the quota, routing, cache, and collaboration-infrastructure findings above record the company's reflections. My own support, reservations, and later reflections on those positions still need to be developed.

My assessment of the March–April MCP work is that broad coverage coexisted with poor interface quality and unresolved permissions design. I linked the usability problems to directly wrapping existing service APIs; repeated pagination calls consumed substantial context during data retrieval. These are my observations and judgments, not a recorded company consensus.

My broader judgment of this stage is that the company emphasized the idea that everyone could create agents while overlooking the need to provide shared AI-native infrastructure. I link that omission to the widespread sense I recall in March–April that AI project progress was below expectations. Nearly all departmental OpenClaw deployments were discontinued during this period; their individual shutdown reasons have not yet been documented. This is my assessment of the gap between ambition and delivery, rather than a recorded company conclusion or a quantified result across all projects.

I regard Project S as a highly idealistic initiative and the founder's April involvement as part of the company's continuing aggressive push. My explanation for the rollout difference centers on simpler permissions at Anuttacon and much more complex permissions at miHoYo. I considered making work-derived memory visible to an entire team and concentrating all work entry points in IM too aggressive for miHoYo. This judgment is distinct from any formal company evaluation, which has not yet been documented.

I describe May–July as a period of less aggressive company-level promotion alongside widespread employee and departmental harness work and infrastructure improvement. I observed MCP refactoring and additions to retrieval, permissions, and memory capabilities. I also regarded the OpenCode-based framework and the memory project I drove as popular internally. The framework's initial appeal to non-R&D staff and later partial acceptance among R&D staff are observations of reception; measured delivery gains and the extent of earlier problem resolution remain open.

When I joined miHoYo, I regarded Claude Sonnet 4.5 as the strongest model available. [Anthropic's announcement](https://www.anthropic.com/news/claude-sonnet-4-5) confirms its release on September 29, 2025. That supports the timing; the judgment about model quality is mine.

My favorable assessment of ByteDance's tools concerns certain long tasks. Their reliability, task duration, human intervention, and business impact still need detail. The basis for my knowledge of their state by the end of 2025 also needs to be documented; this account does not establish that I remained employed there at that time.

## Working Hypotheses Across Cases

The following hypotheses are draft analysis pending my review and further evidence. They are distinct from the personal judgments above and from miHoYo's own conclusions.

**Access and adoption:** The contrast between limited attention to Dify and broad Echo use raises a hypothesis: the effort needed to get started may matter alongside platform availability. This draws on my explanation of Echo's UI. The products' purposes, audiences, rollout conditions, and observation periods have not been matched, so it does not establish a general advantage for client agents over server-side platforms.

**Where to invest development effort:** The sequence moves from shared-platform discussion and client-agent adoption to aggressive framework and skill reuse, widespread discontinuation of departmental deployments, and then May–July harness and infrastructure work. C04–C09 provide a basis for examining which shared capabilities and company-level responsibilities sustain employee-created agents. This sequence does not establish the reasons for individual shutdowns or the company attitude change, the effects on the December proposal and Echo, or the contribution of each investment to later results.

**From tasks to workflows:** C04 separates adoption of individual tasks from the intended integration of work across employees. The proposition to test is whether comprehensive skills can support reliable handoffs and complete workflows. More projects and skills alone do not establish that result.

**Experimentation and cost:** C05 combines a willingness to absorb a large exploration cost with company reflection on quota logic, routing and cache efficiency, and collaboration infrastructure. This raises a question to test alongside C04: what supporting infrastructure is still needed when reusing general-purpose frameworks and skills? The review findings, the experiment's value, and the effectiveness of subsequent corrective actions need separate assessment. Identifying deficiencies does not establish that they were corrected or what value the experiment delivered.

**MCP coverage and usable access:** C06 suggests assessing integration coverage separately from task completion, context consumption, and usable permissions. The later refactoring and capability additions provide a basis for before-and-after evaluation. Neither broad coverage nor the amount of rework alone establishes that the tools and access model support complete workflows.

**Transferring a team agent across organizations:** C06 and C07 suggest testing how existing permissions and work practices affect adoption before treating progress in a startup as evidence for a larger organization. An agent's access to source data and each employee's access to the resulting memory are separate design decisions. The Project S comparison raises these questions without isolating the contribution of each factor or establishing that team memory itself cannot work.

**Harness work and verification:** The May–July focus on context and delivery infrastructure, together with C08, raises a question about what is needed around an existing agent to make long tasks dependable. C08 links front-end and back-end deployment with agent verification through browser use or Playwright, and raises the possibility that this capability changes R&D acceptance. Concrete verification tasks and results are still needed to assess these propositions, especially for work involving several people or agents.

**Personal memory portability and team memory:** C09 addresses continuity for one person across endpoints and agents, while C07 sought team-wide visibility into work-derived memory. They suggest evaluating portability and shared visibility as distinct requirements. C09's reception does not establish that it resolves C07's organizational and permissions difficulties.

## Decision Options for Our Current Company

These are provisional options derived from the cases, pending my review and assessment against our company's priorities and constraints. They are not finalized recommendations or a record of measures miHoYo implemented.

- **Broader adoption — C03:** If broader use among non-R&D staff is a priority, test an accessible general-purpose agent interface with a small set of representative tasks. Assess the effort to complete a first useful task, repeat use, and task quality before expanding.
- **Framework and skill reuse — C04:** If this approach is under consideration, test complete workflows with representative handoffs between employees. Assess completion quality and required human intervention before treating a collection of skills as a complete workflow. Assign company-level owners for shared infrastructure gaps exposed by these tasks, and track continued use and completed workflows after launch. The current cases do not establish a basis for stopping all internal general-purpose agent development.
- **Experimental consumption and infrastructure — C05:** Set experiment budgets and gateway usage limits; cap agent numbers and the message history passed between them; pause or review runs at defined thresholds. Assess routing and KV cache hit rates, and identify infrastructure needs for multi-agent and A2A collaboration. Record spending, intended learning, actual results, and the effects of corrective actions together. Thresholds and infrastructure priorities should reflect our resources and objectives.

- **MCP quality and permissions — C06:** Evaluate representative agent tasks, including the calls and context needed to retrieve data through paginated interfaces. Define which systems personal and team agents may access, and check those boundaries in the same task evaluations. Use completion quality, context consumption, and access problems to guide interface and permissions improvements.

- **Team workflows and memory — C07:** Start with a defined team and a limited set of workflows. Specify the agent's data access and who may see each part of its memory, then evaluate task results and the effort required to change existing work practices. Assess whether moving work into IM improves completion before requiring a full migration. Expand only after the permissions and workflow questions have been resolved for the tested scope.

- **Long-task delivery and verification — C08 and the May–July phase:** Choose a representative task spanning development, deployment, and release. Specify the context provided to the agent, the result that must be verified, and any handoffs between people or agents. Assess completion quality, human intervention, and acceptance among the intended user groups before broadening use.

- **Personal memory portability — C09:** Test a concrete task continued on another endpoint or with another agent. Specify which memory should carry over and its access boundaries, then assess continuity and the effort required to restate context. Evaluate team-wide sharing separately where it is required.

The assessment should distinguish infrastructure availability, application breadth, actual use, workflow completion, and cost relative to results. C03 records Echo's adoption success in my assessment; C04 spans early adoption and widespread discontinuation. C06 covers rollout problems and later rework; C07 concerns organizational fit. C08 adds changing reception as delivery and verification capabilities developed, while C09 adds personal memory portability. Popularity and capability availability still need to be connected to measured business value.

## Information to Complete Before Finalizing

- My formal role title, complete employment dates, and the full review period.
- Decisions, owners, resources, schedules, priority workflows, integration with existing systems, delivery results, and organizational reflection following the December discussion.
- The data-team project's purpose, rationale, actions, results, and my reflections; whether it is related to the later memory project in C09.
- Dify's deployment date, observation period, usage evidence, and explanations for its limited attention.
- Echo's team, start and rollout dates, non-R&D tasks, onboarding changes, adoption and retention evidence, business results, distribution and support, formal sponsorship, later decisions, infrastructure links, and company and personal reflections.
- Exact dates and project coverage for the expansion and subsequent discontinuation; the mapping between projects and deployments, whether Echo was included, who decided to discontinue each deployment and why, and results delivered before shutdown; evidence of skill reuse and completed workflows across employees.
- The teams and experiences behind the widespread perception of disappointing progress in March–April, the expectations being used, measured progress, and any formal company assessment of the infrastructure gap or shutdowns.
- Who communicated the positions on general-purpose agent development and everyone being able to create agents, through which channels and with what scope, and which projects or resource decisions changed.
- The dates of the RMB 2 million incident and its review; the experiment's task, technical outcome, business value, billing records, accounting basis, and cost breakdown; review records, routing and cache measurements, and the specific multi-agent and A2A infrastructure gaps; prior authorization and corrective actions, owners, timing, and effects; my views at the time and in retrospect.
- The March–April MCP inventory, design and deployment coverage, usage, quality criteria, representative tasks and pagination overhead; definitions of personal and team agents and how long specific access questions remained unresolved; the May–July refactoring scope and design changes, retrieval capabilities, permissions coverage, and before-and-after results; owners, company decisions, and timing and links to the broader expansion and cost-incident review.
- Concrete signs of the less aggressive company approach in May–July, any formal policy or resource changes and their reasons; representative harness work, context arrangements, and outcomes for tasks involving multiple people or agents.
- C08's project and department, dates, representative browser verification tasks and acceptance criteria, actual deliveries, human involvement, adoption and retention by user group, quality, and cost.
- C09's name, my responsibilities, dates, supported endpoints and agents, memory content and transfer mechanism, access boundaries, representative tasks, adoption and delivery outcomes, and my reflections.
- My role in or source of knowledge about Project S and the Anuttacon rollout; launch, pilot, and outcome dates; teams involved, workflows actually migrated, permissions conflicts, memory visibility, IM requirements, and measured results; the final miHoYo status and any company review; its relationship to earlier agent initiatives.
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
| U07 | My account of Project S and its differing rollout experiences | Recorded September 17, 2026 | A founder's April 2026 involvement; Claude Code harness work and IM integration; the goal of migrating a team's or department's workflows, shared memory built from conversations, meetings and documents, and access combining all members' data permissions; smoother initial progress at Anuttacon and failure to advance the intended rollout at miHoYo. Startup permissions, miHoYo's complexity, and the assessment that the design was too aggressive are my explanations. My involvement, detailed rollout evidence, final status, and company evaluation remain to be documented. |
| U08 | My account of disappointing progress and confirmation that departmental OpenClaw deployments stopped being used | Recorded September 17, 2026 | The company's belief that anyone could create agents; my assessment that it neglected company-level AI-native infrastructure and that this contributed to disappointing progress; my recollection of widespread concern about AI project progress in March–April 2026; nearly all departmental OpenClaw deployments taken offline and no longer used. Specific deployments, dates, reasons, decision-makers, whether Echo was included, and measured results remain open. These are my recollections and judgments, not independently verified findings or a formal company review. |
| U09 | My account of May–July harness work, infrastructure improvements, and two departmental projects, with clarification of verification | Recorded September 17, 2026 | A less aggressive company-level approach; employee and departmental context work using Codex, Claude Code, and pi agent; exploration of delivery involving multiple people or agents; refactoring of nearly all previously rushed MCP interfaces; retrieval, agent permissions, and memory capabilities. An OpenCode-based development-to-release framework was popular with non-R&D staff and later gained some R&D acceptance as end-to-end verification was added. Its front-end and back-end deployment let engineers ask agents to verify the output using browser use or Playwright. I drove a popular personal memory project enabling transfer across endpoints and agents. These are my recollections, participation, and assessments; formal policy, detailed implementation, measured outcomes, and links to earlier initiatives remain unverified or incomplete. |
| S01 | Anthropic, [Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5) | Published September 29, 2025; accessed September 17, 2026 | Confirms release before my joining month. It does not verify internal company adoption or establish the strongest model across all tasks in November 2025. |
| S02 | OpenClaw documentation, [OpenClaw lore](https://docs.openclaw.ai/start/lore) | Publication date not stated; accessed September 17, 2026 | Records adoption of the OpenClaw name on January 30, 2026, after earlier names. Supports naming chronology, not the timing or extent of popularity in China or Echo's dates and implementation. |
| S03 | Kimi Help Center, [What Is Kimi Agent? Features and Entry Points](https://www.kimi.com/en/help/agent/agent-overview) | Publication date not stated; accessed September 17, 2026 | Places Kimi Claw's public beta in mid-February 2026. My comparison is a product analogy; it establishes neither a January Kimi Claw release nor Echo's precise launch date. |
| S04 | Anthropic, [Introducing Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6) | Published February 5, 2026; accessed September 17, 2026 | Confirms the public release date. Provides model timeline context only, without corroborating the miHoYo incident, amount, mechanism, or company response. |
| S05 | Anuttacon, [About Anuttacon](https://www.anuttacon.com/about/) | Publication date not stated; accessed September 17, 2026 | Confirms the organization's name and its self-description as an independent AI research lab. Does not substantiate the founder connection, Project S, permissions design, rollout outcomes, or business results. |
