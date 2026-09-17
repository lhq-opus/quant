# From Agent Adoption to End-to-End Delivery: Decisions and Lessons from miHoYo

**Language:** English | [Chinese version](report.zh-CN.md)

**Status and scope:** Working draft for leadership review. I draw on my agent development work at miHoYo and my observations from November 2025 through July 2026. The intended one-year retrospective's full boundaries and my formal role title remain to be confirmed.

## Executive View

I saw miHoYo move from a small number of agent initiatives into an aggressive “all in” phase. Employees began using agents widely for individual tasks, while the company expected existing frameworks and employee-written skills to connect those tasks into complete workflows. My assessment is that this approach neglected company-level infrastructure designed for agents. Broad adoption and expanding MCP coverage coexisted with usability, permissions, and delivery problems.

By May–July, the company's approach was less aggressive, while employees and departments focused on harness engineering and the infrastructure required for long tasks. MCP interfaces were reworked, and knowledge retrieval, permissions, and memory capabilities were developed. One departmental framework offered development, deployment, and verification; a separate project enabled personal memory portability. Connecting individual gains into workflows involving multiple people or agents remained an objective under exploration.

The central progression is **all-in adoption with insufficient attention to agent infrastructure → individual-task productivity as the immediate focus → stronger agent infrastructure → attempts to connect work end to end**. These priorities overlapped: the workflow ambition was present early, and Project S attempted team-wide integration in April, before the May–July infrastructure work. The cases below follow that chronology; they do not establish company-wide workflow completion.

| Case | Period | Decision focus | Key result in my account |
| --- | --- | --- | --- |
| 1 | November–December 2025 | Discuss a shared platform from a limited starting point | A platform direction was discussed; implementation remains unconfirmed. |
| 2 | After the January 2026 OpenClaw surge | Make a general-purpose agent accessible through Echo | Broad uptake, especially outside R&D. |
| 3 | The two to three months after Echo; exact dates open | Scale existing frameworks and employee-written skills | Widespread individual-task use; a major cost incident exposed infrastructure gaps. |
| 4 | March–April 2026; overlapping the expansion | Expose internal systems through MCP | Poor usability and unresolved permissions; disappointing progress and widespread departmental OpenClaw discontinuation. |
| 5 | April 2026 initiative | Test a general-purpose harness and team-memory data flywheel through Project S | Smoother initial progress at Anuttacon; the intended miHoYo rollout did not progress. |
| 6 | May–July 2026 | Build the context, infrastructure, and verification needed for delivery | Infrastructure rework and popular departmental projects; broader workflow results remain to be demonstrated. |

**Basis of the analysis:** I participated in data-team agent work, the December discussion, the cost-incident review, and the personal memory initiative. Other developments reflect my observations and recollections, recorded on September 17, 2026. Company positions, my own assessments, and possible explanations are distinguished below. Passages marked **working analysis** and the decision options remain drafts for my review. Internal developments have not been independently corroborated here; public sources support only the external background described in the source table.

## Case Study 1 — November–December 2025: A Shared-Platform Starting Point

### Decisions and Actions

I joined miHoYo's data team in November 2025 to develop agents. To my knowledge, my project was one of very few across the company. A privately deployed Dify instance was available but attracted little attention throughout the period I observed. By December, I understood the company-level infrastructure to consist of an LLM gateway and Dify, alongside a few projects.

I discussed a general-purpose server-side agent platform, a skill hub, and knowledge bases with the head of the shared team. The aim was to help employees move their business workflows onto the platform or complete end-to-end work more effectively over the following months. I describe this leader's seniority as “founder minus one” and considered the discussion partly representative of senior leadership's thinking. The description does not establish a specific reporting line; “shared team” is a provisional English translation.

### Possible Reasons

**Recorded objective:** Provide a common platform and supporting capabilities for employee workflows.

**Working analysis:** With only a few agent projects, a shared platform could offer a way to make capabilities reusable across the company. That is a possible rationale for the proposal, not a documented leadership explanation. Dify's limited attention alone does not establish its suitability for those goals or explain its reception.

For comparison, ByteDance, where I worked earlier, began applying LLMs to customer service and internal engineering productivity in late 2023, then expanded into other areas. By the end of 2025, some tools could complete certain long tasks end to end, with results I considered very good. I therefore regarded miHoYo's start as late. This is my comparative judgment, not an industry ranking; those earlier LLM applications were not all necessarily agents. When I joined miHoYo, I regarded Sonnet 4.5 as the strongest model available; its September 29, 2025 release confirms the timing, not that ranking.

### Key Results

- Shared infrastructure and a platform direction were discussed; formal approval, resourcing, delivery, and the relationship to Dify remain unconfirmed.
- Dify's availability did not translate into much attention in my observation. Usage and business value are not yet measured here.
- My data-team project provides an early example of agent work, but its goal, delivery milestones, and outcomes still need to be developed.

*Evidence: U01, U02, S01.*

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

*This case covers the two to three months after Echo's turning point. Its exact boundaries and the incident-review date remain open; it overlaps the March–April case that follows.*

### Decisions and Actions

I saw the company become highly aggressive about LLMs and agents and invest substantial resources. As I understood the direction, existing frameworks were already good enough, so further general-purpose agent development was unnecessary. Everyone could create agents by writing sufficiently complete skills; the eventual ambition was to connect employees' work into end-to-end workflows.

Departments adapted OpenClaw, while employees moved scattered tasks into agents connected to workplace IM chatbots. In its response to the cost incident below, the company treated the expense as a necessary cost of exploring LLMs. I participated in that review.

### Possible Reasons

**The company's position as I understood it:** Available frameworks reduced the need to develop another general-purpose agent; employee-written skills were expected to encode business work and support broader integration.

**Working analysis:** Echo's broad uptake and the availability of capable frameworks may have made rapid expansion appear feasible. This approach could mobilize many employees quickly. The assumption to examine is whether sufficiently complete skills could turn useful individual tasks into dependable workflows across people and agents. Adoption alone would not test that assumption. The formal source of the framework-and-skills direction remains to be documented, and my personal view of the company's tolerance for the cost incident is still open.

### Key Results

- At least four or five departmental OpenClaw adaptations appeared. Individual-task use and IM integration became widespread; company-wide workflow completion was not established.
- One employee's multi-agent experiment using Opus 4.6 incurred **RMB 2 million in token costs in one day**. The gateway did not cap this experiment's usage, and the experiment had no limits on agent numbers or inter-agent message-history volume. I associate the consumption with those missing limits; billing records and a cost breakdown remain unavailable in this report.
- The company review I attended identified inadequate gateway quota logic, routing problems causing a low **KV cache hit rate**, and missing infrastructure for **multi-agent and agent-to-agent (A2A) collaboration**.
- The expense was accepted as exploration cost, but the experiment's technical and business value, corrective actions, and their effects remain unspecified. Acceptance of the expense does not establish a successful experiment.

*Evidence: U04, U05. S04 supplies the Opus 4.6 release date, not verification of the incident.*

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

**My assessment:** Simpler permissions helped at Anuttacon. At miHoYo, complex permissions were the largest obstacle. I considered the ambition highly idealistic, and the requirements for team-wide memory visibility and moving every work entry point into IM too aggressive for that setting. In particular, I attribute the unsuccessful rollout to three design gaps:

1. **Agents were treated as team employees without a corresponding permissions system.** The employee-like role and intended access were not supported by an agent permissions design.
2. **Team memory lacked isolation.** The team memory system did not establish the isolation needed for that setting. The specific boundaries requiring isolation still need to be documented.
3. **The general-purpose harness layer was too weak.** At the time of recording this retrospective, my view is that no existing harness framework fits every project. This is my technical judgment; a systematic comparison of frameworks is outside the evidence assembled here.

**Working analysis:** Progress in the startup may have made the model appear transferable. The comparison points to the need to evaluate agent authority, memory boundaries, and workflow-specific harness capabilities before extending a design across organizations. Per-user pods and unisolated team memory coexist in my account, so the execution layout should not be taken as evidence of memory isolation. The available evidence does not isolate each gap's contribution or show that team memory itself is unworkable.

### Key Results

- I recall smoother initial progress at Anuttacon; complete migration or measured business value there has not been established.
- The intended miHoYo rollout did not progress. Its final status, pilot scope, and whether any parts remained in use are still unclear.
- Project S was an early attempt to connect individual assistance into team workflows through a reusable harness and accumulated memory. This account does not yet provide evidence that the memory pipeline improved subsequent tasks or produced a working data flywheel. The failure explanations above are my assessment, not a formal company postmortem.

*Evidence: U07. S05 supports Anuttacon's name and stated research focus only.*

## Case Study 6 — May–July 2026: Building Infrastructure to Connect Individual Gains

### Decisions and Actions

At the company level, I observed a less aggressive approach. Employees and departments nevertheless commonly pursued harness engineering: when using Codex, Claude Code, or pi agent, they explored what context would better constrain agents to complete long tasks. They also examined what infrastructure was needed for end-to-end delivery involving multiple people or agents.

During these three months, nearly all MCP interfaces previously rushed into use were refactored. Knowledge-base retrieval, an agent permissions system, and agent memory capabilities were added or developed. The infrastructure effort now addressed how agents would use knowledge, access systems, and retain context.

Two departmental projects gave this work concrete forms:

**An OpenCode-based delivery framework.** The framework offered development, deployment, and release end to end. By providing both front-end and back-end deployment, it allowed engineers to ask an agent to verify the output through browser use or Playwright. This describes an available verification path, not a record of a particular successful test or unattended production release.

**The personal memory system I drove.** I advanced a project addressing one person's collaboration across multiple endpoints and agents. Memory could move from one endpoint to another and from one agent to another. This addressed personal continuity, a different requirement from Project S's team-wide visibility. The technical relationship between the systems, and the memory project's relationship to my original data-team project, remain unconfirmed.

### Possible Reasons

**Working analysis:** The earlier cases expose a gap between creating an agent and giving it the conditions to finish work. The May–July focus could reflect greater attention to those conditions: relevant knowledge, usable tools, permitted access, persistent context, and a way to verify outputs. Together, these capabilities could make it more practical to connect individual tasks.

The OpenCode case also suggests that verification can matter to R&D acceptance alongside generation and deployment. A runnable application and a way for agents to check it may have made generated work easier for engineers to evaluate. These are possible explanations for the priorities and reception; the reasons for the company attitude change, any formal policy or resource changes, and links to earlier corrective actions remain to be established.

### Key Results

- I observed infrastructure rework and new supporting capabilities. Their rollout scope and measured effect on task completion are still open; refactoring does not establish that every earlier issue was resolved.
- The OpenCode-based project was initially popular with non-R&D colleagues. After adding agent end-to-end verification, it also gained **some acceptance among R&D staff**.
- I regarded the memory project I drove as another popular departmental initiative. It provided **memory portability across endpoints and agents**; adoption figures and business impact remain unmeasured here.
- These projects provided capabilities relevant to linking work, but the broader goal of dependable workflows across multiple people and agents remained under exploration. This account does not yet demonstrate company-wide completion of that transition.

*Evidence: U09. The initiatives share the May–July period; their precise internal sequence and delivery dates remain open.*

## Decision Implications for Our Company

The cases suggest that individual adoption, agent infrastructure, and workflow integration need separate evaluation. The options below are **working analysis for my review**, to be tested against our company's priorities and constraints; they are not a record of measures miHoYo implemented.

| Decision area | Basis | Option to test |
| --- | --- | --- |
| Adoption | Case 2 | Use an accessible interface for representative non-R&D tasks; measure the effort to complete a first useful task, repeat use, and output quality. |
| Framework reuse and shared infrastructure | Cases 3, 4, 5, 6 | Evaluate a complete workflow alongside its skills, separating reusable harness functions from workflow-specific requirements. Assign owners for tool usability, knowledge retrieval, permissions, and memory. Measure calls, context consumption, completion quality, and sustained use. Existing frameworks alone do not settle what internal development is still needed. |
| Experimental cost and operations | Case 3 | Set budgets, gateway limits, agent-count and message-history caps, and review thresholds. Assess routing, KV cache efficiency, and multi-agent/A2A needs; record spending, learning, and results together. |
| Team workflow integration | Cases 5, 6 | Start with a bounded team and workflow. Define handoffs, agent roles and permissions, source-data access, and memory isolation and visibility separately. Test whether accumulated memory improves subsequent tasks, alongside the value and disruption of moving work into IM, before requiring broad migration. |
| Delivery and verification | Case 6 | Test a development-to-deployment task with explicit acceptance criteria and agent verification. Evaluate completed work, human intervention, cost, and acceptance by the intended user groups. |
| Personal memory continuity | Case 6 | Continue a real task on another endpoint or agent. Check what memory transfers, access boundaries, and the effort needed to restate context. Treat team-wide sharing as a separate requirement. |

## Evidence Needed to Strengthen the Conclusions

- **Baseline and early adoption:** My formal title, employment dates, and full review period; the data-team project's purpose and results; December action items, owners, resources, and delivery; Dify's observation period and usage; Echo's dates, team, tasks, retention, business results, and relationship to the platform proposal.
- **Expansion and the incident:** The source and scope of the framework-and-skills direction; project names, departments, dates, skill reuse, handoffs, and completed workflows; incident and review dates, billing basis, authorization, cost breakdown, routing/cache measurements, experiment value, and corrective actions.
- **March–April outcomes:** Which deployments stopped, who decided, why, whether Echo was included, and what had been delivered; the teams and expectations behind disappointing progress; MCP inventory, deployment and use, pagination overhead, quality criteria, and the definitions and unresolved permissions of personal and team agents.
- **Project S:** My role or source of knowledge; pilot scope, component deployment, and dates in both companies; actual workflow migration, final status, and any formal company review. Specific agent permissions gaps, required memory isolation boundaries, missing harness capabilities, permissions conflicts, and memory visibility and IM requirements in practice. Similarity thresholds, memory-processing quality, retrieval and reuse by agents, and effects on subsequent task outcomes.
- **May–July:** Specific policy or resource changes and their reasons; harness tasks and multi-person/multi-agent results; refactoring changes, retrieval and permissions coverage, and before-and-after outcomes. For the delivery framework, a representative verification run, acceptance criteria, and adoption by user group. For my memory project, my responsibilities, supported endpoints and agents, memory content, transfer mechanism, access boundaries, usage, and task outcomes. Project names, departments, dates, links to earlier initiatives, and my further reflections remain to be added.
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
| U07 | My account of Project S, its architecture, rollout differences, and design gaps | Recorded September 17, 2026 | A founder's April 2026 involvement; a general-purpose Claude Code harness and team-memory data flywheel; IM integration and the goal of migrating team workflows, with shared memory from conversations, meetings, and documents and intended access to all members' data. My architecture account covers per-user pods, CC coordinator/worker/researcher roles, session and IM record collection, similarity-based memory processing, and scheduled vault maintenance. I recall smoother initial progress at Anuttacon and failure to advance the intended miHoYo rollout. Simpler startup permissions, miHoYo's complexity, aggressive IM and visibility requirements, absent agent permissions design, unisolated memory, and a weak generic harness are my explanations. The absence of a universally applicable harness is my technical judgment at the time of this retrospective. My involvement, component deployment, detailed results, final status, and company evaluation remain to be documented; the architecture and outcomes have not been independently verified. |
| U08 | My account of disappointing progress and confirmation that departmental OpenClaw deployments stopped being used | Recorded September 17, 2026 | The company's belief that anyone could create agents; my assessment that it neglected company-level AI-native infrastructure and that this contributed to disappointing progress; my recollection of widespread concern about AI project progress in March–April 2026; nearly all departmental OpenClaw deployments taken offline and no longer used. Specific deployments, dates, reasons, decision-makers, whether Echo was included, and measured results remain open. These are my recollections and judgments, not independently verified findings or a formal company review. |
| U09 | My account of May–July harness work, infrastructure improvements, and two departmental projects, with clarification of verification | Recorded September 17, 2026 | A less aggressive company-level approach; employee and departmental context work using Codex, Claude Code, and pi agent; exploration of delivery involving multiple people or agents; refactoring of nearly all previously rushed MCP interfaces; retrieval, agent permissions, and memory capabilities. An OpenCode-based development-to-release framework was popular with non-R&D staff and later gained some R&D acceptance as end-to-end verification was added. Its front-end and back-end deployment let engineers ask agents to verify the output using browser use or Playwright. I drove a popular personal memory project enabling transfer across endpoints and agents. These are my recollections, participation, and assessments; formal policy, detailed implementation, measured outcomes, and links to earlier initiatives remain unverified or incomplete. |
| S01 | Anthropic, [Introducing Claude Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5) | Published September 29, 2025; accessed September 17, 2026 | Confirms release before my joining month. It does not verify internal company adoption or establish the strongest model across all tasks in November 2025. |
| S02 | OpenClaw documentation, [OpenClaw lore](https://docs.openclaw.ai/start/lore) | Publication date not stated; accessed September 17, 2026 | Records adoption of the OpenClaw name on January 30, 2026, after earlier names. Supports naming chronology, not the timing or extent of popularity in China or Echo's dates and implementation. |
| S03 | Kimi Help Center, [What Is Kimi Agent? Features and Entry Points](https://www.kimi.com/en/help/agent/agent-overview) | Publication date not stated; accessed September 17, 2026 | Places Kimi Claw's public beta in mid-February 2026. My comparison is a product analogy; it establishes neither a January Kimi Claw release nor Echo's precise launch date. |
| S04 | Anthropic, [Introducing Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6) | Published February 5, 2026; accessed September 17, 2026 | Confirms the public release date. Provides model timeline context only, without corroborating the miHoYo incident, amount, mechanism, or company response. |
| S05 | Anuttacon, [About Anuttacon](https://www.anuttacon.com/about/) | Publication date not stated; accessed September 17, 2026 | Confirms the organization's name and its self-description as an independent AI research lab. Does not substantiate the founder connection, Project S, permissions design, rollout outcomes, or business results. |
