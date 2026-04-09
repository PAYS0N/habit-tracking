# Daily Checkin — Project Status

Project tasks are managed centrally via the personal assistant CLI:

    /home/payson/Documents/repos/self/personal-assistant/scripts/project_tasks_cli.py

Project slug: `daily-checkin`

Commands:
- `project_tasks_cli.py list daily-checkin` — list open tasks
- `project_tasks_cli.py add daily-checkin "<name>" [--severity S] [--difficulty D]  [--value V]` — add a task
- `project_tasks_cli.py complete daily-checkin <task_id>` — mark done
- `project_tasks_cli.py update daily-checkin <task_id> [--name N] [--severity S] [--difficulty D]  [--value V]` — update
- `project_tasks_cli.py delete daily-checkin <task_id>` — delete
