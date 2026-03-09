Compose a prompt for a new session task to do the indicated work item. 
Include all the context someone would need, both practically (ex point to a specific kotlin file) and management wise (point to any helpful cdocs). 
The prompt should likely include an instruction to read project_management/manifest.md. 
The prompt should indicate the following workflow item in addition to the task definition: 

- Run this checklist after the user has declared the task done (make it clear to run this after completion is externally confirmed, not when it thinks it's done.):

    1. **status.md** — remove the item from Open; add any newly discovered open items.
    2. **manifest.md** — add a row for every new file created; remove rows for deleted files.
    3. **context docs** — Read cdoc.md. Update only the context file affected by the change.
    4. **Response to user** - remind the user to make a git commit.

Indicate the Claude model best suited for the task, not as part of the prompt. 
The created prompt should be output to the user, not a markdown doc.