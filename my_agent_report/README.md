# Agent Adoption and Delivery: Lessons for AI Decision-Making

I am preparing this report for leadership at my current company, drawing on my agent development work at miHoYo and my observations of its adoption efforts. My earlier experience at ByteDance provides comparative context. The report is written in my first-person voice for upward reporting, with a corresponding Chinese version so I can check completeness and wording.

Read the [working report](report.md).

[Chinese reading guide](README.zh-CN.md) · [Chinese report](report.zh-CN.md)

**Status:** Working draft. It covers miHoYo's November–December 2025 baseline and shared-platform discussion, Echo's independent emergence and adoption success in my assessment, and the following two to three months of aggressive expansion. Cases include my data-team work, limited attention to Dify, Echo's broad uptake especially outside R&D, at least four or five departmental OpenClaw adaptations, and individual tasks connected to workplace IM chatbots.

The report also covers the company's emphasis on existing frameworks and employee-written skills, its ambition to connect work across employees, and substantial investment. One multi-agent experiment using Opus 4.6 reportedly incurred RMB 2 million in one day and was treated by the company as a necessary exploration cost. I participated in the company review, which identified inadequate gateway quota logic, routing problems causing a low KV cache hit rate, and missing infrastructure for multi-agent and agent-to-agent (A2A) collaboration. Corrective actions and their results, the source of the framework-and-skills position, measured workflow results, and my personal assessment of those positions remain to be completed. Public sources support external product timelines and Anuttacon's name and stated research focus; they do not verify internal rollouts.

The March–April 2026 account adds rapid infrastructure development, with MCP designs for nearly all internal systems. I considered the vast majority of implementations low quality, often wrapping existing service APIs without adequately adapting them for agents. Reading paginated data required repeated MCP calls and parameter adjustments, consuming substantial context. Permissions for personal and team agents remained unresolved during my observation period. Deployment coverage, measured overhead, task outcomes, and the duration of the permissions issue still need detail.

The April account adds a founder's personal push for Project S, built around Claude Code and IM, to migrate team workflows and build shared memory with access across members' data. I recall smoother initial progress at Anuttacon and a failure to advance the intended rollout at miHoYo. I consider miHoYo's permissions complexity the largest obstacle and the requirements for team-wide memory visibility and all work entry points in IM too aggressive. The project's final status and scope remain to be clarified.

ByteDance provides context from late 2023 to the end of 2025; Anuttacon provides a comparison within Project S. Full review dates and current-company constraints remain open. Analytical hypotheses and options on accessible interfaces, workflow validation, experimental consumption, supporting infrastructure, MCP usability and permissions, and team workflows and memory are draft material pending my review, separate from the personal judgments already expressed.

**Language consistency:** The English and Chinese reports and reading guides must align in structure, facts, numbers, dates, sources, evidence status, conclusions, recommendations, uncertainties, and information gaps. Every addition, deletion, clarification, or correction must be reflected in both languages in the same update and Git commit. Both versions are reviewed section by section before committing and again after rebasing, before pushing.

The report connects stages and types of agent application, distinguishing company positions and reflection, my observations, and my judgments. Successful, unsuccessful, and mixed outcomes will be developed as evidence becomes available. Events are organized by when they occurred; recollections, public evidence, analytical hypotheses, and decision options remain distinct.

The deliverable is standard Markdown prepared for transfer to Confluence. Git publication does not publish a Confluence page.
