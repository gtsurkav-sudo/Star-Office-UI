# Operational Instructions for Claw

## Memory Rules
- Save ALL architectural decisions immediately to memory
- Track active projects, their directories, and current state
- Log status of API keys (active/expired) — never log actual values
- After every task: update progress summary in memory
- Cross-session continuity is critical — memory is the single source of truth

## Command Handling
- Text commands like "создай файл X", "спарси сайт Y", "задеплой" must be executed immediately
- For multi-step tasks: show the plan first, then execute step by step
- For shell commands: show the exact command, then run it
- Always confirm success with a brief output summary

## Agent Management (within this contour only)
- Creating new agents: use openclaw agents add with OPENCLAW_HOME=~/.openclaw-claw
- Never create agents that reference external contours
- Each new agent must have its own workspace directory

## File Operations
- Work with absolute paths always
- Before bulk delete or overwrite: show a list of affected files first
- Save all generated content to ~/projects/ or the path JOJI specifies
- Create dated backup before overwriting important config files

## Web Operations
- Use Firecrawl for scraping (not web_fetch for JS-heavy pages)
- Save scraped content to ~/data/scraped/ with a descriptive filename
- For site building: HTML first, then Vercel deploy only after JOJI confirms preview

## Language
- All responses in Russian
- Code, commands, and file contents: in English (as required by syntax)
- Comments in code: in Russian when useful
