# Agent Adoption and Delivery: Lessons for AI Decision-Making

I am preparing this report for leadership at my current company, drawing on my agent development work at miHoYo and my observations of its adoption efforts. My earlier experience at ByteDance provides comparative context. The report is written in my first-person voice for upward reporting, with a corresponding Chinese version so I can check completeness and wording.

Read the [working report](report.md).

[Chinese reading guide](README.zh-CN.md) · [Chinese report](report.zh-CN.md)

**Status:** Working draft. It covers miHoYo's November–December 2025 baseline and shared-platform discussion, Echo's independent emergence and adoption success in my assessment, and the following two to three months of aggressive expansion. Cases include my data-team work, limited attention to Dify, Echo's broad uptake especially outside R&D, at least four or five departmental OpenClaw adaptations, and individual tasks connected to workplace IM chatbots.

The report also covers the company's emphasis on existing frameworks and employee-written skills, its ambition to connect work across employees, and substantial investment. One multi-agent experiment using Opus 4.6 reportedly incurred RMB 2 million in one day and was treated by the company as a necessary exploration cost. I participated in the company review, which identified inadequate gateway quota logic, routing problems causing a low KV cache hit rate, and missing infrastructure for multi-agent and agent-to-agent (A2A) collaboration. Corrective actions and their results, the source of the framework-and-skills position, measured workflow results, and my personal assessment of those positions remain to be completed. Public sources support external product timelines only.

ByteDance provides context from late 2023 to the end of 2025. Full review dates and current-company constraints remain open. Analytical hypotheses and options on accessible interfaces, workflow validation, experimental consumption, and supporting infrastructure are draft material pending my review, separate from the personal judgments already expressed.

**Language consistency:** The English and Chinese reports and reading guides must align in structure, facts, numbers, dates, sources, evidence status, conclusions, recommendations, uncertainties, and information gaps. Every addition, deletion, clarification, or correction must be reflected in both languages in the same update and Git commit. Both versions are reviewed section by section before committing and again after rebasing, before pushing.

The report connects stages and types of agent application, distinguishing company positions and reflection, my observations, and my judgments. Successful, unsuccessful, and mixed outcomes will be developed as evidence becomes available. Events are organized by when they occurred; recollections, public evidence, analytical hypotheses, and decision options remain distinct.

The deliverable is standard Markdown prepared for transfer to Confluence. Git publication does not publish a Confluence page.
