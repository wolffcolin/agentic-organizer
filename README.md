# agentic-organizer

Student Folder Organizer (CSCI 598, Group 5). You point the agent at a messy school folder. It runs in a
read-only sandbox, proposes renames and moves, and pulls out deadlines and to-dos. Nothing changes until
you approve, and the approved deadlines become a weekly plan and a calendar file.

| Part | Owner | Directory |
| --- | --- | --- |
| Organizer (file readers, classifier, executor + undo) | Amari Bullock | `organizer/` |
| Extractor (deadlines, conflicts, local/Claude routing) | Colin Wolff | `extractor/` |
| Planner and interface (Electron app, weekly view, .ics) | Gunnar Bozentko | `app/` |

The JSON handoff shared by all three parts is drafted in [`shared/handoff.schema.json`](shared/handoff.schema.json),
with synthetic examples in [`shared/examples/sample-records.json`](shared/examples/sample-records.json).
**Do not commit real user files.**

## Running the app

Requires Node.js 20+.

```bash
cd app
npm install
npm run dev      # launch the Electron app (uses mock data by default)
npm test         # unit tests
```

Set `ORGANIZER_BACKEND=real` to use the real organizer/executor once it exists. The default `mock` backend never
modifies files.
