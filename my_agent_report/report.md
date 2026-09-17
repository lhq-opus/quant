# From Agent Adoption to End-to-End Delivery: Decisions and Lessons from miHoYo

**Language:** English | [Chinese version](report.zh-CN.md)

**Status and scope:** Working draft for leadership review. The core account covers my agent work and observations at miHoYo from November 2025 through July 2026, followed by an update on Anuttacon in approximately August–September 2026. Earlier public information supplies context for that separate company. The intended one-year retrospective's full boundaries and my formal role title remain to be confirmed.

## Executive View

Project S helped colleagues design warehouse tables. I spent roughly two months adapting data engineering from requirement tickets through tables, SQL, and acceptance. The workflow was used for a period, with frequent human intervention. Every stage had agent acceptance, yet business criteria remained the main bottleneck: data engineers with deeper business knowledge had to adjust them, and data and table quality were difficult to quantify through one standard. Where new instrumentation data had to return, the game projects I worked with were also constrained by major-version cycles typically longer than a month. Organizational rollout faced separate gaps in agent permissions and team-memory isolation. These concrete limits underpin my concern about moving from individual productivity to end-to-end delivery.

The company had already seen broad uptake of Echo and rapid gains on individual tasks. By May–July, work shifted toward the conditions those tasks needed when joined together: reworking MCP interfaces, adding retrieval and permissions, preserving memory, and making generated applications available for agent verification. The OpenCode-based framework gained some R&D acceptance after verification was added. These are specific advances; they do not yet establish reliable completion of the full data workflow I worked on.

The central progression is **all-in adoption with insufficient attention to agent infrastructure → individual-task productivity as the immediate focus → stronger agent infrastructure → attempts to connect work end to end**. These priorities overlapped: the workflow ambition was present early, and Project S attempted team-wide integration in April, before the May–July infrastructure work. The cases below follow that chronology; they do not establish company-wide workflow completion.

| Case | Period | Decision focus | Key result in my account |
| --- | --- | --- | --- |
| 1 | November–December 2025 | Discuss a shared platform from a limited starting point | A platform direction was discussed; implementation remains unconfirmed. |
| 2 | After the January 2026 OpenClaw surge | Make a general-purpose agent accessible through Echo | Broad uptake, especially outside R&D. |
| 3 | February–April 2026 productivity priority; wider expansion dates open | Improve individual engineering productivity through clients and skills; halt nearly all server-side agent projects | Rapid single-task gains in my assessment; a major cost incident exposed infrastructure gaps. |
| 4 | March–April 2026; overlapping the expansion | Expose internal systems through MCP | Poor usability and unresolved permissions; disappointing progress and widespread departmental OpenClaw discontinuation. |
| 5 | April 2026 initiative | Test a general-purpose harness and team-memory data flywheel through Project S | Useful on individual data tasks; the intended miHoYo rollout did not progress. |
| 6 | May–July 2026; project restart dates open | Develop harnesses and delivery infrastructure; seek B2B experience for FDE responsibilities | Infrastructure rework and popular departmental projects; broader workflow results remain to be demonstrated. |
| 7 | Approximately August–September 2026; Anuttacon, a separate company | Add FDE support while promoting its own models to investor-backed companies | My account of recruitment from miHoYo and an internal draft on FDE responsibilities; customer delivery and model-improvement results remain open. |

**Basis of the analysis:** I participated in data-team agent work, the December discussion, the cost-incident review, Project S workflow adaptation, and the personal memory initiative. Other developments reflect my observations and information available to me, recorded on September 17, 2026. Company positions, my assessments, and possible explanations are distinguished below. Passages marked **working analysis** and the decision options remain drafts for my review. Public product pages, research, and announcements support the external context in Case Study 7; they do not independently verify the internal miHoYo cases or Anuttacon's recent FDE recruitment. The FDE principles image is an internal draft, not a recruitment announcement or evidence of completed customer work.

## Case Study 1 — November–December 2025: A Shared-Platform Starting Point

### Decisions and Actions

I joined miHoYo's data team in November 2025 to develop agents. To my knowledge, my project was one of very few across the company. A privately deployed Dify instance was available but attracted little attention throughout the period I observed. By December, I understood the company-level infrastructure to consist of an LLM gateway and Dify, alongside a few projects.

**Early staffing direction:** The company initially recruited people with agent development experience to build its own agent runtime frameworks. The exact recruitment dates and staffing arrangements remain to be documented.

I discussed a general-purpose server-side agent platform, a skill hub, and knowledge bases with the head of the shared team. The aim was to help employees move their business workflows onto the platform or complete end-to-end work more effectively over the following months. I describe this leader's seniority as “founder minus one” and considered the discussion partly representative of senior leadership's thinking. The description does not establish a specific reporting line; “shared team” is a provisional English translation.

### Possible Reasons

**Recorded objective:** Provide a common platform and supporting capabilities for employee workflows.

**Working analysis:** With only a few agent projects, a shared platform could offer a way to make capabilities reusable across the company. That is a possible rationale for the proposal, not a documented leadership explanation. Dify's limited attention alone does not establish its suitability for those goals or explain its reception.

For comparison, ByteDance, where I worked earlier, began applying LLMs to customer service and internal engineering productivity in late 2023, then expanded into other areas. By the end of 2025, some tools could complete certain long tasks end to end, with results I considered very good. I therefore regarded miHoYo's start as late. This is my comparative judgment, not an industry ranking; those earlier LLM applications were not all necessarily agents. When I joined miHoYo, I regarded Sonnet 4.5 as the strongest model available; its September 29, 2025 release confirms the timing, not that ranking.

### Key Results

- Shared infrastructure and a platform direction were discussed; formal approval, resourcing, delivery, and the relationship to Dify remain unconfirmed.
- Dify's availability did not translate into much attention in my observation. Usage and business value are not yet measured here.
- My data-team project provides an early example of agent work, but its goal, delivery milestones, and outcomes still need to be developed.

*Evidence: U01, U02, U10, S01.*

## Case Study 2 — After the January 2026 OpenClaw Surge: Echo Makes Agents Accessible

### Decisions and Actions

Another team independently initiated Echo, a general-purpose agent running on users' clients, after the OpenClaw surge in China that I place in January 2026. This was a separate project line from the December platform discussion.

Its form reminded me of Kimi Claw and, retrospectively, the ChatGPT client available when I recorded this account in September 2026. These are product analogies; they do not establish Echo's launch date, architecture, or technical dependencies.

### Possible Reasons

**My assessment:** Echo's client UI substantially reduced the effort needed to get started, particularly for non-R&D colleagues. I regard that as a major reason for its broad uptake.

**Working analysis:** An accessible client may have made the value of a general-purpose agent easier to experience than the earlier platform offering. The comparison does not control for use cases, audiences, or rollout conditions, so this is not evidence that client agents are generally superior to server-side platforms.

### Key Results

- I observed widespread use, especially among non-R&D staff, and consider Echo a company-level adoption success.
- Echo marked a turning point in my account. Whether its success directly drove particular later management decisions remains unconfirmed.
- Retention, task-level time savings, business impact, sponsorship, and its subsequent roadmap still need evidence.

*Evidence: U03. S02 and S03 provide naming and product timeline context, not independent confirmation of Echo's rollout.*

## Case Study 3 — The Months After Echo: “All In” on Frameworks and Skills

*I place the individual engineering-productivity priority in February–April 2026. My earlier account dates the wider expansion to the two to three months after Echo's turning point; its exact boundaries and the incident-review date remain open. This case overlaps the March–April case that follows.*

### Decisions and Actions

I saw the company become highly aggressive about LLMs and agents and invest substantial resources. As I understood the direction, existing frameworks were already good enough, so further general-purpose agent development was unnecessary. Everyone could create agents by writing sufficiently complete skills; the eventual ambition was to connect employees' work into end-to-end workflows.

During February–April, the immediate priority was improving individual employees' engineering productivity. In my observation, colleagues familiar with the business did this better using agent clients. The company also halted **nearly all server-side agent projects**. The overlap with the departmental OpenClaw deployments in Case Study 4 remains to be established.

Departments adapted OpenClaw, while employees moved scattered tasks into agents connected to workplace IM chatbots. In its response to the cost incident below, the company treated the expense as a necessary cost of exploring LLMs. I participated in that review.

### Possible Reasons

**The company's position as I understood it:** Available frameworks reduced the need to develop another general-purpose agent; employee-written skills were expected to encode business work and support broader integration.

**Working analysis:** Echo's broad uptake and the availability of capable frameworks may have made rapid expansion appear feasible. This approach could mobilize many employees quickly. The assumption to examine is whether sufficiently complete skills could turn useful individual tasks into dependable workflows across people and agents. Adoption alone would not test that assumption. The formal source of the framework-and-skills direction remains to be documented, and my personal view of the company's tolerance for the cost incident is still open.

### Key Results

- My assessment is that employees' single-task productivity problems were resolved rapidly, within **two to three months**. The task coverage, criteria for considering them resolved, and measured gains remain to be documented.
- At least four or five departmental OpenClaw adaptations appeared. Individual-task use and IM integration became widespread; company-wide workflow completion was not established.
- One employee's multi-agent experiment using Opus 4.6 incurred **RMB 2 million in token costs in one day**. The gateway did not cap this experiment's usage, and the experiment had no limits on agent numbers or inter-agent message-history volume. I associate the consumption with those missing limits; billing records and a cost breakdown remain unavailable in this report.
- The company review I attended identified inadequate gateway quota logic, routing problems causing a low **KV cache hit rate**, and missing infrastructure for **multi-agent and agent-to-agent (A2A) collaboration**.
- The expense was accepted as exploration cost, but the experiment's technical and business value, corrective actions, and their effects remain unspecified. Acceptance of the expense does not establish a successful experiment.

*Evidence: U04, U05, U10. S04 supplies the Opus 4.6 release date, not verification of the incident.*

## Case Study 4 — March–April 2026: Broad Integration Without Adequate Agent Infrastructure

### Decisions and Actions

Company-level infrastructure expanded quickly. Nearly all internal systems had MCP interfaces designed for them, and many implementations rapidly exposed capabilities by wrapping existing service APIs. In my account of this stage, which systems personal and team agents should access remained unresolved.

The wider approach still emphasized everyone being able to create agents. My assessment is that company-level infrastructure designed for agent workflows was neglected, even as MCP coverage expanded.

### Possible Reasons

**My assessment:** Many wrappers retained interfaces suited to human use but poorly suited to agents. I connect the resulting infrastructure gap with the widespread sense I recall that AI project delivery was falling short of expectations.

**Working analysis:** Reusing existing APIs offered a fast route to exposing tools, but availability may have been easier to achieve than usable access for long tasks. Skills could describe work without resolving those underlying constraints. This is an explanation to examine, not a documented company conclusion or proof of the cause of every project shutdown.

### Key Results

- I considered the vast majority of MCP implementations low quality. When reading data, agents repeatedly called tools and adjusted pagination parameters, consuming substantial context. Concrete call counts and task impact remain unmeasured here.
- Permissions for personal and team agents were still unclear. Broad interface coverage did not settle who could access what.
- I recall a widespread sense in March–April that AI projects were progressing below expectations. This is my observation of sentiment, not a survey or a quantified result across every project.
- Nearly all departmental OpenClaw deployments were taken offline and **stopped being used**. The individual reasons, decision-makers, mapping to the earlier project count, and whether Echo was included remain open.

*Evidence: U06, U08. The May–July rework is the follow-up in Case Study 6.*

## Case Study 5 — April 2026: Project S Tests a General-Purpose Harness and Data Flywheel

### Decisions and Actions

A miHoYo founder personally promoted Project S while the company's approach was still highly aggressive. I understand it as an attempt to combine a **general-purpose harness framework with a team-memory data flywheel**. Built around Claude Code, it integrated workplace IM and aimed to move every person's workflows within a team or department into the system.

**What harness means here.** I use the term for the code and configuration around an agent that provide task context, tool access, continuity between steps, and a way to check its work. Access controls and the execution environment make that system usable within a company. Claude Code supplied the underlying agent; Project S added request routing, worker/researcher roles, and Vault memory. Those additions still needed permissions, memory boundaries, and acceptance checks suited to each workflow. An external example is Anthropic's [long-running agent harness](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), which combined recorded progress, explicit feature requirements, and browser tests. That illustrates the term, without verifying Project S's implementation.

**My implementation work.** While on the data team, I spent roughly two months carrying out forward-deployed engineer (FDE) responsibilities, adapting data engineers' workflows to Project S. Their existing process started with a requirement ticket, usually involved processing data already collected through instrumentation, and followed development standards in the team's knowledge base to create warehouse tables and write SQL. The work then went to testing for acceptance. The migration aimed for agents to collect requirements and data, create tables, write SQL, and perform acceptance, with **criteria and agent checks at every stage**.

My responsibilities included designing skills, hooks, subagent responsibilities, workflow decomposition, mechanisms for applying acceptance criteria, and how acceptance results would drive further workflow iteration, as well as memory and knowledge retrieval. The goal was for the agent to complete the entire task. The precise dates and the extent to which that goal was achieved still need further documentation.

**My view of the FDE boundary:** Business teams define and revise acceptance criteria. My responsibility is to provide high-quality infrastructure that makes the model follow those criteria as reliably as possible. I consider this an important FDE principle: not defining the criteria on the business team's behalf or teaching them how to do their business. The acceptance mechanisms implement the criteria the business team supplies.

Routine data engineering usually processed existing data; the broader workflow I worked to support also included instrumentation design and returned data:

```text
Understand the requirement
  -> Collect the requirements context
  -> Design data instrumentation
  -> Receive data generated by the instrumentation
  -> Design the data warehouse table
  -> Run data processing and validate results
```

The intended design combined:

- Team memory drawn from conversations between people and between people and agents, meetings, documents, and other work material.
- Memory visible to every team member and an agent with all members' data permissions.
- All work entry points concentrated in IM so the agent could capture complete workflow context.

**Architecture as I recall it.** A pod pool provided one pod per user. Each pod contained one Claude Code coordinator that distributed user requests to other Claude Code agents with roles such as worker and researcher. The following is a logical sketch; the deployment scope of each component in the two companies remains to be documented. CC stands for Claude Code.

```text
Pod pool: one pod per user
|
+-- User 1 -> Pod 1
|              |
|              +-- User requests -> Coordinator (one CC)
|                                      |
|                                      +--> Worker (CC)
|                                      +--> Researcher (CC)
|                                      +--> Other roles (CC)
|
+-- User 2 -> Pod 2 (same internal layout)
+-- ...    -> ...   (same internal layout)

Session records ------------+
                            +--> Collector
Agent IM group chat logs ---+        |
                                     | synchronize
                                     v
                               Vault Manager
                                     |
                       Similarity from vector retrieval
                                     |
        +----------------------------+------------------------+
        | High                       | Medium                 | Low
        v                            v                        v
Discard incoming record    Merge with existing node    New node + links
                                     |                        |
                                     +------------+-----------+
                                                  v
                                         Vault (team memory)
                                                  ^
                                                  |
                                         Scheduled inspection
                                         Merge / update / delete
```

Collectors gathered session records and records from IM groups in which agents participated, then synchronized them to the Vault Manager. It used vector-retrieval similarity to decide how to handle incoming material: **high similarity meant discarding it; medium similarity meant merging it with an existing node; low similarity meant creating a new node and links between nodes**. The vault also had scheduled inspections to merge, update, and delete memory data.

The flywheel ambition was to turn ongoing work records into reusable team context. The retrieval path back to agents, ingestion of meetings and documents, and evidence of better subsequent task outcomes remain to be documented.

As I understand it, the founder first promoted the project at Anuttacon, his other LLM company. I describe Anuttacon as a startup with a relatively simple permissions system, where initial progress was smoother.

### Possible Reasons

**The design rationale in my account:** Reuse a common harness across projects and accumulate context from team work, with IM as the common entry point.

**My assessment of organizational rollout:** Simpler permissions helped at Anuttacon. At miHoYo, complex permissions were the largest obstacle to rollout. I considered the ambition highly idealistic, and the requirements for team-wide memory visibility and moving every work entry point into IM too aggressive for that setting. In particular, I attribute the unsuccessful rollout to three design gaps:

1. **Agents were treated as team employees without a corresponding permissions system.** The employee-like role and intended access were not supported by an agent permissions design.
2. **Team memory lacked isolation.** The team memory system did not establish the isolation needed for that setting. The specific boundaries requiring isolation still need to be documented.
3. **The general-purpose harness layer was too weak.** At the time of recording this retrospective, my view is that no existing harness framework fits every project. This is my technical judgment; a systematic comparison of frameworks is outside the evidence assembled here.

**Problems and changes during actual use.** Connecting these steps required repeated revision and self-verification by agents, which I found placed high demands on the harness and agent infrastructure. People intervened frequently during use. These three classes of problems come from my implementation experience:

| Observed problem | Change made | Known effect and limits |
| --- | --- | --- |
| Delegation to a subagent lost key context from the main agent. | Use the memory system to recover missing context. | Memory was used to repair handoffs. What was retained, how it was read, and before-and-after performance remain to be documented. This does not establish a working team-memory data flywheel. |
| With long contexts, the model did not follow skills consistently. | Assign deterministic procedures to hooks, usually maintained through scripts. | A subagent stop hook can run data-quality scripts. After a failed check, the main agent replans the work; the specific checks, retry rules, and completion conditions remain to be documented. |
| Performance and cost were problematic; data engineers commonly said the workflow took too long. | Make workflow changes and downgrade subagent models. | I observed some relief, but elapsed time, cost, and quality after model downgrades have not been compared quantitatively here. |

**A concrete point for running checks.** A subagent stop hook can run data-quality scripts. Some scripts come from testing; others come from the workflow's ongoing self-iteration. After a failed check, the main agent replans the work. This illustrates how the results of deterministic checks inform subsequent work allocation. The specific reassignment, retry and completion rules, and how scripts produced through iteration enter the checks still need to be documented.

**The main bottleneck after use: business acceptance.** Even with checks at each stage, the data engineers who knew the business better had to adjust the criteria. Data quality and table quality were difficult to judge through one quantitative standard. This prevented rapid self-iteration: after connecting the execution steps, deciding whether a revision was better still required business judgment. Ambiguous criteria could cause goal drift in my assessment; this account does not yet reconstruct a particular drift incident.

**Another constraint: waiting for real data.** In the game projects I worked with, instrumentation data returned on a major-version cycle, typically longer than a month, limiting verification and iteration speed. Tasks processing existing data and tasks waiting for new data need to be considered separately. The exact stage of the wait and the checks that could be completed earlier remain to be documented.

**Why this still fell short of reliable end-to-end delivery — working analysis.** Context recovery, hooks, and workflow changes addressed handoffs, adherence, and execution overhead respectively. They could not independently decide which data results met the business need or shorten the game's release cycle. In this case, reliable acceptance required both business specialists able to express and revise their criteria and data against which to check the result. Measuring only table creation or SQL-writing speed would omit the time spent adjusting acceptance and waiting for feedback.

**Working analysis:** Progress in the startup may have made the Project S design appear transferable. The comparison points to the need to evaluate agent authority, memory boundaries, and workflow-specific harness capabilities before extending a design across organizations. Per-user pods and unisolated team memory coexist in my account, so the execution layout should not be taken as evidence of memory isolation. The available evidence does not isolate each gap's contribution or show that team memory itself is unworkable.

### Key Results

- In my FDE work, I found Project S performed well on real individual requests, such as designing a data warehouse table. This is my qualitative assessment; measured task results remain to be documented.
- The adapted data engineering workflow was used for a period, with frequent human intervention. Memory, hooks, workflow changes, and model downgrades addressed actual problems. Business acceptance and data-return cycles continued to limit rapid self-iteration; dependable completion without human intervention has not been demonstrated here.
- I recall smoother initial progress at Anuttacon; complete migration or measured business value there has not been established.
- The intended miHoYo rollout did not progress. Its final status, pilot scope, and whether any parts remained in use are still unclear.
- Project S was an early attempt to connect individual assistance into team workflows through a reusable harness and accumulated memory. This account does not yet provide evidence that the memory pipeline improved subsequent tasks or produced a working data flywheel. The failure explanations above are my assessment, not a formal company postmortem.

*Evidence: U06, U07, U12, U13, U14, S05, S11. The problem-and-change table comes from my implementation account; measured effects remain open. The FDE boundary reflects my approach to the role; explanations of the conditions for delivery are marked as working analysis. S05 supplies organizational context; S11 supplies an external harness example.*

## Case Study 6 — May–July 2026: Building Infrastructure to Connect Individual Gains

### Decisions and Actions

At the company level, I observed a less aggressive approach. Employees and departments nevertheless commonly pursued harness engineering: when using Codex, Claude Code, or pi agent, they explored what context would better constrain agents to complete long tasks. They also examined what infrastructure was needed for end-to-end delivery involving multiple people or agents.

Agent project activity also resumed, with the focus shifting from developing agent runtimes to **harness engineering on mature existing frameworks**. The company now wanted agent developers with **B2B experience** to take on responsibilities similar to those of a forward-deployed engineer (FDE).

During these three months, nearly all MCP interfaces previously rushed into use were refactored. Knowledge-base retrieval, an agent permissions system, and agent memory capabilities were added or developed. The infrastructure effort now addressed how agents would use knowledge, access systems, and retain context.

Two departmental projects gave this work concrete forms:

**An OpenCode-based delivery framework.** The framework offered development, deployment, and release end to end. By providing both front-end and back-end deployment, it allowed engineers to ask an agent to verify the output through browser use or Playwright. This describes an available verification path, not a record of a particular successful test or unattended production release.

**The personal memory system I drove.** I advanced a project addressing one person's collaboration across multiple endpoints and agents. Memory could move from one endpoint to another and from one agent to another. This addressed personal continuity, a different requirement from Project S's team-wide visibility. The technical relationship between the systems, and the memory project's relationship to my original data-team project, remain unconfirmed.

### Possible Reasons

**My interpretation of the change:** I connect the return to agent projects with the rapid resolution of the individual productivity problems described in Case Study 3.

**Working analysis of the shift:** Client adoption and warehouse table design had shown useful results. The remaining problems were specific: MCP data retrieval required repeated pagination; employee-like agents lacked defined authority; team memory lacked isolation. My data engineering adaptation also encountered subagent context loss, poor skill adherence, and lengthy workflows, calling for memory, hooks, and workflow and model adjustments respectively. Running data-quality scripts from a subagent stop hook is a concrete way to integrate existing checks into a mature framework. Business teams define and revise acceptance criteria; FDEs provide the infrastructure and execution mechanisms that make models follow them as reliably as possible. The workflow also has to account for when real data becomes available. That helps explain the demand for FDE experience in understanding customer environments, adapting infrastructure, and improving model adherence. It is a case-based explanation, not a documented company statement of why it changed course.

The implementations addressed different parts of the work. Project S distributed requests and collected context. MCP rework addressed tool access. The personal memory project supported continuity across endpoints and agents. OpenCode exposed a running application for browser inspection, and gained some R&D acceptance after verification was added. This last case is a partial positive comparison: it added an executable check after code generation and deployment. It does not establish that browser checks can settle the business definitions, instrumentation, and data validation in Project S's workflow. Specific verification results and human intervention remain to be documented, as do formal policy and resource changes and links to corrective actions from the cost review.

### Key Results

- I observed infrastructure rework and new supporting capabilities. Their rollout scope and measured effect on task completion are still open; refactoring does not establish that every earlier issue was resolved.
- The OpenCode-based project was initially popular with non-R&D colleagues. After adding agent end-to-end verification, it also gained **some acceptance among R&D staff**.
- I regarded the memory project I drove as another popular departmental initiative. It provided **memory portability across endpoints and agents**; adoption figures and business impact remain unmeasured here.
- These projects provided capabilities relevant to linking work, but the broader goal of dependable workflows across multiple people and agents remained under exploration. This account does not yet demonstrate company-wide completion of that transition.

*Evidence: U09, U10; the analysis of the shift also draws on U12, U13, and U14. The infrastructure and departmental initiatives share the May–July period; their precise internal sequence and delivery dates remain open. The calendar dates of the broader return to agent projects and staffing changes also need confirmation.*

## Case Study 7 — Approximately August–September 2026: Anuttacon Needs FDE Support to Put Its Models to Work

### Decisions and Actions

In the month before this account, I learned that Anuttacon was recruiting people from within miHoYo to carry out FDE work using models it had developed itself, serving companies backed by investors. **The need arose while promoting its models: FDE support was needed to help enterprises use them.** I do not describe this as a pivot into an FDE services business. The particular investors, customer companies, models, and hiring outcomes remain unspecified.

Anuttacon's internal **[Draft] AI FDE Principles** records preliminary conclusions about this role. It puts customer business value first, asks FDEs to work alongside users and carry solutions through to sustained use, and calls for feedback from that work to improve models. The principles are intended to guide both staff decisions and AI suggestions, plans, and execution. The document is a draft; the recruitment information comes from my account, not from the image.

**Public context, separate from the recent FDE account.** In September 2024, PEdaily reported that it had confirmed Cai Haoyu's involvement in Anuttacon with multiple investors. This establishes a reported connection to the miHoYo founder, not a shared corporate structure. [PEdaily's original report](https://news.pedaily.cn/202409/539580.shtml)

| Date | Publicly documented work or change | What it adds to this case |
| --- | --- | --- |
| August 2025 | Anuttacon released *Whispers from the Star*, an interactive story using real-time AI dialogue with the character Stella. The developer's page describes text, voice, and video interaction. [Steam product page](https://store.steampowered.com/app/3730100) | A released conversational AI product; its existence does not establish enterprise workflow delivery. |
| April 9, 2026 | The LPM 1.0 paper describes a 17-billion-parameter video performance model and a streaming version for characters speaking, listening, and reacting. [Original paper](https://arxiv.org/abs/2604.07823) | Concrete model research associated with Anuttacon: the company connection is supported by [project lead Ailing Zeng's profile](https://ailingzeng.site/) and [Shanghai Securities News reporting](https://www.cnstock.com/commonDetail/668962). LPM is a video model; these sources do not identify the model used in the recent enterprise FDE work. |
| Shutdown effective July 29, 2026, at 11:59 p.m. PDT | AnuNeko was permanently shut down; the team's notice says it redirected resources. [Official notice](https://anuneko.com/) | A confirmed product closure and resource decision. The notice does not specify FDE as the destination of those resources. |

### Possible Reasons

**Purpose as I understand it:** Anuttacon recognized that promoting its models required people who could help customers apply them to actual work. The internal draft makes that support more specific than demonstrating a model or supplying an endpoint.

**Working analysis — reading the six draft principles against the miHoYo cases:**

| Draft principle | What it asks of an FDE | Concrete comparison in this report |
| --- | --- | --- |
| Value | Agree on a business result and how to measure it: revenue, cost, or quality. | Echo's broad use and Project S's useful table designs are positive observations; neither supplies a measured result for the complete data workflow. |
| Leverage | Work with users, locate a consequential bottleneck, and test a small change. | I used memory to address subagent context loss and workflow/model adjustments to ease lengthy execution reported by data engineers. Business acceptance remained the main bottleneck afterward. |
| AI-Native | Use agents in research, construction, and testing, guided by human judgment. | Project S used specialized Claude Code agents; OpenCode let agents verify deployed output through a browser. Business acceptance still needs an explicit basis. |
| Ownership | Follow through until a solution is used, delivers value, and can keep operating. | In the data workflow, delivering a table design leaves returned data, processing, and the original requirement to reconcile. |
| Data Flywheel | Use actual usage and feedback to improve the model, with criteria for evaluating progress. | Project S collected work records, but this account has no evidence of model training or of those records improving later task results. |
| Generalization | Train capabilities shared across customer problems into the foundation model and evaluate them across companies. | The portability of Project S's harness was itself a difficulty. A model learning a reusable capability would need evidence from different customers, not just one workflow. |

The two proposed data cycles have different mechanisms. Project S aimed to turn conversations and IM logs into Vault memory for later retrieval. The Anuttacon draft additionally calls for learning from customer work and training shared capabilities into a model. **Working analysis:** collecting conversation logs does not establish that usable task outcomes and acceptance judgments have been captured. The current Project S account does not explain how that feedback was produced. The draft gives a reason to connect FDE delivery with model improvement; it does not establish that this learning cycle already works.

### Key Results

- I can report a recently recognized need for FDE support, recruitment from miHoYo, and preliminary internal conclusions about the role. This supplements its model promotion.
- Public sources document conversational products, video-model research, and a product shutdown. They do not independently confirm the recent recruitment, identify the enterprise model or customers, or establish successful enterprise delivery.
- The next results to look for are an accepted customer workflow and a demonstrated improvement from its feedback. Neither is yet available in this account. The draft's model-improvement and cross-company generalization principles remain objectives to test.

*Evidence: U11, D01, S06–S10; the miHoYo workflow comparison also draws on U12. The principle-to-case mapping and explanation of the two data cycles are working analysis. Anuttacon's FDE requirement and miHoYo's move toward harness engineering are different decisions in different companies.*

## Decision Implications for Our Company

The following options are **working analysis for my review**, subject to our company's priorities and constraints. Each starts from a specific case; they are not measures that miHoYo or Anuttacon has been shown to have completed.

| Case evidence | Decision to test | Evidence to collect |
| --- | --- | --- |
| Echo spread widely, but its business impact is unmeasured here. | Pick a recurring task for the intended user group before expanding access. | Whether people return to it, whether the output is accepted, and how much work remains after the agent finishes. |
| Data engineers defined and revised Project S's business criteria; my FDE responsibility was model adherence. | Have the business team supply acceptance criteria and the FDE provide infrastructure to carry and apply them. First examine model behavior with the criteria held constant, then evaluate harness changes. | Which existing requirements were omitted or misapplied, and whether adherence and human intervention improve after execution mechanisms change. Record any business revisions to the criteria separately. |
| Subagent context loss, poor skill adherence, and lengthy execution each needed specific changes. | On representative tasks, examine memory handoffs, hook execution, and the effects of workflow and subagent model adjustments separately. | Context retained, required steps executed, human intervention, total time and cost, and any quality change after model downgrades. |
| Feedback requiring new instrumentation data could be constrained by a major-version cycle longer than a month. | Before a pilot, distinguish checks possible with existing data from those that must wait for new data; schedule validation and intermediate delivery accordingly. | Time spent on computation, human work, and waiting for data, and which final results were verified against real data. |
| MCP wrappers required repeated pagination. | Compare the old and revised interfaces on the same data request before expanding tool coverage. | Tool calls, context consumed, completeness of retrieved data, and whether the next workflow step can use the result. |
| Project S assigned employee-like roles without matching permissions and exposed unisolated team memory. | Define what each agent may access and which people may retrieve each memory before expanding the pilot. | Allowed and denied access across the intended boundaries; whether the workflow can complete with those limits in place. |
| OpenCode gained some R&D acceptance after browser verification was added. | Make the deployed application and agreed checks part of the delivery, alongside the code. | A representative browser test, defects found and corrected, and the intended user's acceptance. Keep business judgments visible where a browser test cannot settle them. |
| The multi-agent experiment incurred RMB 2 million in one day. | Establish gateway and experiment budgets, agent and message-history limits, and review thresholds before repeating such experiments. | Spending, useful output, routing/cache behavior, and whether the limits stop further consumption as intended. |
| My personal memory project supported changes of endpoint and agent. | Continue a real task through such a switch with the original access boundaries. | What context survives, what must be explained again, and whether the final result remains correct. |
| Anuttacon recognized a need for FDE while promoting its models. | If our model rollout also needs customer adaptation, consider the division above: customers define business acceptance criteria; FDEs provide infrastructure and ensure model adherence. If model training is intended, retain evaluated task outcomes and distinguish model errors from tool, access, or context defects. | A used and accepted workflow first; then evidence that feedback improves performance on a separate task or customer. A collected conversation alone is insufficient. |

## Evidence Needed to Strengthen the Conclusions

- **Baseline and early adoption:** My formal title, employment dates, and full review period; the data-team project's purpose and results; December action items, owners, resources, and delivery; Dify's observation period and usage; Echo's dates, team, tasks, retention, business results, and relationship to the platform proposal.
- **Expansion and the incident:** The source and scope of the framework-and-skills direction; project names, departments, dates, skill reuse, handoffs, and completed workflows; incident and review dates, billing basis, authorization, cost breakdown, routing/cache measurements, experiment value, and corrective actions.
- **March–April outcomes:** Which deployments stopped, who decided, why, whether Echo was included, and what had been delivered; the teams and expectations behind disappointing progress; MCP inventory, deployment and use, pagination overhead, quality criteria, and the definitions and unresolved permissions of personal and team agents.
- **Project S:** The dates of my roughly two months of FDE work, duration of use, pilot scope, completion status, and how I learned about Anuttacon; component deployment, final status, and any formal company review in both companies. The data engineering workflow, three classes of intervention, and FDE boundary are now described; a real ticket's business-supplied criteria, model execution, deviations and fixes, and delivery result remain needed. What memory retained and how subagents accessed it, stop-hook checks, the main agent's specific response after a failure, and retry and completion rules; how scripts from testing or daily iteration enter the checks; how workflows changed, and before-and-after models, intervention, time, cost, and quality. Business revisions to criteria and changes to execution mechanisms need separate records. The precise stage waiting for a major release, affected tasks, and checks possible earlier. Specific agent authority and memory isolation boundaries, permissions conflicts, IM requirements in practice, and Vault similarity thresholds, memory-processing quality, and reuse across tasks also remain open.
- **May–July:** Specific policy or resource changes and their reasons; harness tasks and multi-person/multi-agent results; refactoring changes, retrieval and permissions coverage, and before-and-after outcomes. For the delivery framework, a representative verification run, acceptance criteria, and adoption by user group. For my memory project, my responsibilities, supported endpoints and agents, memory content, transfer mechanism, access boundaries, usage, and task outcomes. Project names, departments, dates, links to earlier initiatives, and my further reflections remain to be added.
- **Staffing and project decisions:** Early recruitment dates, roles, and staffing arrangements; the projects halted in February–April, decision-makers and scope, and their relationship to departmental OpenClaw deployments and Project S. The task coverage, acceptance criteria, and measured gains behind my assessment that individual productivity problems were resolved in two to three months. Dates of renewed project activity, whether it involved existing or new projects, and actual B2B/FDE staffing and delivery outcomes.
- **Anuttacon's model deployment and FDE support:** Exact dates within the recent month, recruitment and customer scope, the investor relationships, and the identity and development basis of the models being promoted. The draft's date, authorship, adoption, representative customer work, acceptance criteria, and any feedback used for training or model evaluation. The public video-model work does not fill these gaps.
- **Comparisons and applicability:** ByteDance's specific tools, task scope, reliability, human involvement, and business impact, plus how I learned about their state by the end of 2025; supporting records for company decisions; the AI decisions and constraints at our current company.

## Sources and Evidence Notes

| ID | Source | Date | Support and limitations |
| --- | --- | --- | --- |
| U01 | My recollections of joining miHoYo and my earlier ByteDance experience | Recorded September 17, 2026 | Joining date, data-team work, company-wide understanding of project scarcity, Dify, earlier employment and comparative timeline, and my personal assessments. Internal company developments have not been independently corroborated here. |
| U02 | My recollection of December 2025 infrastructure and the platform discussion | Recorded September 17, 2026 | LLM gateway, Dify, few projects, discussion with the shared-team head, the seniority I described, proposed platform, skill hub, knowledge bases, and employee use cases. Leadership significance is my interpretation; formal approval and execution remain unconfirmed. |
| U03 | My observations of Echo and its independent project origin | Recorded September 17, 2026 | Emergence after the OpenClaw surge I place in January 2026; another team's self-initiated exploration; client agent; product analogies; broad use, especially outside R&D. Success and the UI explanation are my judgments. Precise dates, measured results, technical dependencies, and formal Echo-specific decisions remain open. |
| U04 | My recollections of expansion after Echo and the multi-agent cost incident | Recorded September 17, 2026 | Following two to three months; at least four or five departmental OpenClaw adaptations; individual-task adoption and IM integration; company emphasis on frameworks and skills; substantial investment; RMB 2 million in one day using Opus 4.6, missing limits, and the company's response. The source of the framework-and-skills position, dates, billing evidence, workflow and experiment outcomes, and my personal evaluation of those company positions remain open. U05 adds my participation in the incident review. |
| U05 | My participation in the company incident review and confirmation of the cost amount | Recorded September 17, 2026 | I participated in the review. Company reflections covered inadequate gateway quota logic, routing problems causing a low KV cache hit rate, and missing infrastructure for multi-agent and A2A collaboration. I confirmed the amount as RMB 2 million. Review records and measurements have not been independently examined here; corrective actions and their effects remain to be documented. |
| U06 | My observations of March–April infrastructure development, MCP quality, pagination, and permissions | Recorded September 17, 2026 | Rapid development in March–April 2026; MCP designs for nearly all internal systems; many wrappers around existing service APIs; my assessment that the vast majority were low quality; repeated MCP calls and pagination adjustments consuming substantial context during data retrieval; unresolved system access for personal and team agents. Deployment coverage, measured overhead, task outcomes, specific permissions questions, and their duration remain open. These are my recollections and judgments, not independently verified results or company review findings. |
| U07 | My Project S workflow adaptation work and my account of its architecture, rollout, and constraints | Recorded September 17, 2026 | A founder's April 2026 involvement; a general-purpose Claude Code harness and team-memory data flywheel; IM integration and the goal of migrating team workflows, with shared memory from conversations, meetings, and documents and intended access to all members' data. My architecture account covers per-user pods, CC coordinator/worker/researcher roles, session and IM record collection, similarity-based memory processing, and scheduled vault maintenance. I recall smoother initial progress at Anuttacon and failure to advance the intended miHoYo rollout. Simpler startup permissions, miHoYo's complexity, aggressive IM and visibility requirements, absent agent permissions design, unisolated memory, and a weak generic harness are my explanations. The absence of a universally applicable harness is my technical judgment at the time of this retrospective. I spent roughly two months on FDE responsibilities in the data team, adapting colleagues' workflows. I found individual requests such as warehouse table design worked well. The workflow I worked to support covered requirements understanding and context collection, instrumentation design, data return, warehouse table design, and processing and validation. Repeated revision and self-verification placed high demands on the harness and agent infrastructure; unclear acceptance criteria could cause goal drift. These are my observations and risk assessment. Exact dates, how I learned about Anuttacon, component deployment, concrete workflow records and measured results, final status, and company evaluation remain to be documented; the architecture and outcomes have not been independently verified. |
| U08 | My account of disappointing progress and confirmation that departmental OpenClaw deployments stopped being used | Recorded September 17, 2026 | The company's belief that anyone could create agents; my assessment that it neglected company-level AI-native infrastructure and that this contributed to disappointing progress; my recollection of widespread concern about AI project progress in March–April 2026; nearly all departmental OpenClaw deployments taken offline and no longer used. Specific deployments, dates, reasons, decision-makers, whether Echo was included, and measured results remain open. These are my recollections and judgments, not independently verified findings or a formal company review. |
| U09 | My account of May–July harness work, infrastructure improvements, and two departmental projects, with clarification of verification | Recorded September 17, 2026 | A less aggressive company-level approach; employee and departmental context work using Codex, Claude Code, and pi agent; exploration of delivery involving multiple people or agents; refactoring of nearly all previously rushed MCP interfaces; retrieval, agent permissions, and memory capabilities. An OpenCode-based development-to-release framework was popular with non-R&D staff and later gained some R&D acceptance as end-to-end verification was added. Its front-end and back-end deployment let engineers ask agents to verify the output using browser use or Playwright. I drove a popular personal memory project enabling transfer across endpoints and agents. These are my recollections, participation, and assessments; formal policy, detailed implementation, measured outcomes, and links to earlier initiatives remain unverified or incomplete. |
| U10 | My account of changing goals, staffing needs, and agent project decisions | Recorded September 17, 2026 | Initial recruitment of people with agent development experience for in-house runtime frameworks; the February–April 2026 focus on individual engineering productivity and a halt to nearly all server-side agent projects. My qualitative assessments cover the better results achieved with agent clients by colleagues familiar with the business, and the resolution of single-task productivity problems within two to three months. I associate that progress with renewed agent project activity focused on harness engineering on mature frameworks, and demand for agent developers with B2B experience to perform FDE responsibilities. Recruitment and restart dates, actual staffing, task coverage and measured gains, halted/new/resumed project identities, and the relationship to OpenClaw deployments and Project S remain open. These are my recollections and interpretations, not independently verified results or a formal company review. |
| U11 | My account of Anuttacon's recent recruitment and need for FDE support, with clarifications | Recorded September 17, 2026; events in approximately August–September 2026 | Anuttacon is recruiting from within miHoYo and needs FDE support while promoting its own models to companies backed by investors. I clarified that this is not a pivot into FDE services, and that the image records internal preliminary conclusions about FDE positioning. Customer identities, investment relationships, model identities, hiring outcomes, and delivered results remain open; the recent activity has not been independently corroborated. |
| U12 | My further account of data engineering workflow adaptation, changes, and use | Recorded September 17, 2026 | Data engineers normally received tickets, processed existing instrumentation data, created tables and SQL under team knowledge-base standards, then handed work to testing. The migration aimed for agents to complete it, with agent acceptance at every stage. My responsibilities covered skills, hooks, subagent/workflow decomposition, acceptance and self-iteration, memory, and retrieval. People intervened frequently: memory addressed subagent context loss, hooks and similar mechanisms addressed poor skill adherence, and workflow changes and model downgrades eased lengthy execution and performance/cost problems. After a period of use, I judged business acceptance the main bottleneck: data engineers had to adjust criteria, and data/table quality was hard to quantify. Instrumentation data in the game projects described depended on a major-version cycle typically longer than a month. This refines U07; it does not establish absent acceptance checks, new instrumentation for every task, a proven memory flywheel, or unattended delivery. Specific tasks, rules, before-and-after measures, stages of waiting, and final delivery remain open and unverified independently. |
| U13 | My clarification of the FDE responsibility boundary | Recorded September 17, 2026 | Business teams define and revise acceptance criteria. My responsibility is to provide sufficiently high-quality infrastructure so models follow those criteria as reliably as possible, without defining the criteria for business teams or teaching them how to do their business. I consider this an important FDE principle; it clarifies acceptance-mechanism design in U12. It is not presented as formal company policy or an industry consensus, nor as proof of perfect adherence. |
| U14 | My account of deterministic procedures, stop hooks, and the sources of check scripts | Recorded September 17, 2026 | Deterministic procedures are assigned to hooks and usually maintained through scripts. A subagent stop hook can run data-quality scripts, sourced from testing and the full workflow's ongoing self-iteration. After a failed check, the main agent replans the work. Specific reassignment, retry and completion behavior, script production and integration, particular task results, and measured effects remain to be documented. It does not establish that the hook blocks exit or that agents may change business criteria themselves. |
| D01 | Image of Anuttacon's internal “[Draft] AI FDE Principles” | Reviewed September 17, 2026; document undated | Value, Leverage, AI-Native, Ownership, Data Flywheel, and Generalization. It covers business outcomes, work alongside users, agent-assisted delivery, sustained use, model improvement from feedback, and training shared capabilities into a foundation model. Company attribution is based on my identification; the image itself has no visible issuer or date. It is a draft, not a hiring notice or proof of implementation and results. |
| S01 | Anthropic, [Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5) | Published September 29, 2025; accessed September 17, 2026 | Confirms release before my joining month. It does not verify internal company adoption or establish the strongest model across all tasks in November 2025. |
| S02 | OpenClaw documentation, [OpenClaw lore](https://docs.openclaw.ai/start/lore) | Publication date not stated; accessed September 17, 2026 | Records adoption of the OpenClaw name on January 30, 2026, after earlier names. Supports naming chronology, not the timing or extent of popularity in China or Echo's dates and implementation. |
| S03 | Kimi Help Center, [What Is Kimi Agent? Features and Entry Points](https://www.kimi.com/en/help/agent/agent-overview) | Publication date not stated; accessed September 17, 2026 | Places Kimi Claw's public beta in mid-February 2026. My comparison is a product analogy; it establishes neither a January Kimi Claw release nor Echo's precise launch date. |
| S04 | Anthropic, [Introducing Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6) | Published February 5, 2026; accessed September 17, 2026 | Confirms the public release date. Provides model timeline context only, without corroborating the miHoYo incident, amount, mechanism, or company response. |
| S05 | Anuttacon, [About Anuttacon](https://www.anuttacon.com/about/) | Publication date not stated; accessed September 17, 2026 | Confirms the organization's name and its self-description as an independent AI research lab. Does not substantiate the founder connection, Project S, permissions design, rollout outcomes, or business results. |
| S06 | PEdaily, Yang Jiyun and Liu Chuan, [Exclusive: Anuttacon emerges as Cai Haoyu's new venture](https://news.pedaily.cn/202409/539580.shtml) | Published September 4, 2024; accessed September 17, 2026 | Original reporting attributing confirmation of Cai's involvement to multiple investors. Supports the reported connection; not corporate control, Project S, or recent FDE recruitment. |
| S07 | Anuttacon, [Whispers from the Star — Steam product page](https://store.steampowered.com/app/3730100) | Lists release on August 14, 2025; accessed September 17, 2026 | Developer and publisher, release, and the developer's description of real-time AI dialogue and text/voice/video interaction. No inference about enterprise delivery or business success. |
| S08 | Ailing Zeng and coauthors, [LPM 1.0: Video-based Character Performance Model](https://arxiv.org/abs/2604.07823) | Submitted April 9, 2026; revised April 14; accessed September 17, 2026 | Authors' account of a 17B video performance model and streaming generation. A video-model research result, not evidence identifying the enterprise FDE model or demonstrating business workflow completion. |
| S09 | [Ailing Zeng's research profile](https://ailingzeng.site/); Luo Maolin, [Shanghai Securities News report on LPM](https://www.cnstock.com/commonDetail/668962) | Profile undated, with April 2026 LPM entry; report April 11, 2026; accessed September 17, 2026 | The researcher describes prior leadership at Anuttacon and lists LPM; the report explicitly associates LPM with the company. Used for the research connection, with S08 supplying technical details. Does not establish current employment or ownership of the models used for FDE. |
| S10 | AnuNeko team, [Shutdown notice](https://anuneko.com/); USPTO, [ANUNEKO application record](https://tmng-al.uspto.gov/resting2/api/casedoc/cms/case/99419248/office-action/OfficeAction8263919.pdf) | Notice publication date unstated; shutdown July 29, 2026, 11:59 p.m. PDT; trademark document February 19, 2026; accessed September 17, 2026 | The official notice confirms permanent shutdown and resource redirection. The trademark document names Anuttacon Pte. Ltd. as the ANUNEKO applicant, supporting the brand connection. Neither establishes that resources went to FDE. |
| S11 | Anthropic, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Published November 26, 2025; accessed September 17, 2026 | Primary engineering example using progress records, requirements, and browser testing around an agent. Used to clarify harness engineering, not to verify miHoYo's implementation or claim universal applicability. |
