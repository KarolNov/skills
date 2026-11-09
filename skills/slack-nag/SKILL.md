---
name: slack-nag
description: Schedule a series of friendly "nagging bot" follow-ups in a Slack thread until someone answers. Takes a thread URL, a short description of what to nag about, and a backoff (e.g. "1 3 5 14" days). Drafts a table of messages and dates, and after confirmation creates one scheduled task per nudge; each task checks the thread first and stays quiet if it's been answered. Use when the user says "nag", "keep nudging", "follow up until they reply", or "/slack-nag".
argument-hint: <slack thread url> "<what to nag about>" <backoff days, e.g. 1 3 5 14>
---

# Slack nagging bot

Arguments: `$ARGUMENTS`

Needs the Slack connector and the scheduled-tasks tool of the Claude desktop app (`create_scheduled_task`). Without them, say which one is missing and stop.

You draft a schedule of follow-up messages in one Slack thread, show it, and only after the user confirms do you create the scheduled tasks. Nothing goes to Slack before that confirmation.

## 1. Parse the input

- **Thread URL**: `https://<workspace>.slack.com/archives/<CHANNEL_ID>/p<DIGITS>`. The parent `ts` is the digits with a dot before the last six: `p1792488185023259` → `1792488185.023259`. If the URL carries `?thread_ts=…`, that value is the parent ts, and the `p…` part is a reply inside the thread.
- **What to nag about**: one short line. It is the subject of every message, e.g. "Dana's sign-off on the Q3 budget" or "the vendor's reply on the contract redlines".
- **Backoff**: one number per nudge, each the gap in days since the previous one; the first gap counts from today. `1 3 5 14` is four nudges: tomorrow, then 3, 5 and 14 days after the one before. A gap of `0` means today's send slot if it's still ahead. Accept words too ("1 day, 3 days, 2 weeks"). With no backoff given, default to `1 3 5 14`.

If anything is missing or unclear, ask once, in one message, before going further.

## 2. Read the thread

Use the Slack connector: `slack_read_thread` with the channel id and parent ts. Work out:

- **Who to nag**: the person who owes the answer, usually whoever was asked or said they'd follow up. They may be a go-between relaying someone else's answer (a customer, a vendor, another team); the nudges still go to the person in the thread. If it's unclear, ask the user. Get their Slack user id (`slack_search_users` if needed).
- **Already answered?** If the thread already holds the answer, say so and stop.
- **The anchor message**: the latest message from the person being nagged in which they said they would act (e.g. "I'll check and get back to you"), or, if they never replied, the message that asked them. Note its `ts`: the scheduled tasks count only replies with a later ts as an answer. Quote it too, for the user's benefit.
- **The user's own Slack user id**: the nudges are posted from their account, so the tasks need it to tell nudges and the user's own messages apart from everyone else's.

## 3. Work out the times

- **Their timezone**: `slack_read_user_profile`. Profiles often don't show a timezone. Then use what the conversation or the thread says (e.g. "they're in Berlin" → `Europe/Berlin`), and otherwise ask. Never guess silently.
- **Your timezone**: the user's IANA zone, e.g. from `readlink /etc/localtime` (macOS/Linux) or `timedatectl`.
- **Send time**: 11:00 in *their* timezone unless the user asks for another time, never before 09:00 or after 17:00 their time.
- **Weekends**: a date that lands on a Saturday or Sunday moves to the following Monday. The next gap counts from the date actually used.
- **Daylight saving**: compute every timestamp with real timezone rules, not a fixed offset. `date` flags differ between macOS and Linux, so use `python3` with `zoneinfo` or `node` with `Intl.DateTimeFormat(…, { timeZone, timeZoneName: 'longOffset' })` to get each date's offset. Regions switch on different dates (or not at all), so the user's local time can shift by an hour from one nudge to the next even though theirs stays at 11:00.

## 4. Draft the messages

One message per nudge, each tagging the person (`<@USERID>`) and opening with 🤖, in the voice of "<first name>'s automated nagging bot", using the first name from the user's own Slack profile (`slack_read_user_profile` with no `user_id`). Keep them light and a little self-aware, and escalate gently:

1. Friendly first check-in: what the question is, and "paste whatever they replied, I'll go back to sleep".
2. Same ask, a joke about persistence.
3. Mention the backoff ("I'm backing off, so you're getting off easy"), and restate the concrete ask.
4. Offer help: a reminder message they can forward, another contact, or a draft.
5. Final nudge: "about to be decommissioned", and name the decision that's due if there's still no answer.

The first nudge always uses 1 and the last always uses 5. With fewer than five nudges, drop from the middle (2, then 3, then 4); with more, add middle ones that vary the jokes rather than repeating them. Any joke about time ("day 4 of my glorious existence") must match the real dates in the schedule. Every message must stand on its own: name the concrete ask in a few words, so someone who hasn't read the thread still knows what's being chased.

## 5. Show the plan and wait

Show one markdown table and nothing scheduled yet:

| # | Their time | Your time | Message |
|---|---|---|---|

Below it, in a few short lines:
- each task reads the thread first and posts nothing once someone has passed on the answer; "still waiting" doesn't count as an answer;
- the first task that finds the answer deletes the nudges still scheduled in this series (saying `go` approves that), and tells you what was said;
- a task that runs late (the app was closed) won't post outside 09:00–17:00 on a weekday, their time; it reschedules itself for the next 11:00 slot instead, and it skips posting if another nudge in the series went out in the last 20 hours, so a backlog never arrives as a burst;
- tasks only run while the Claude desktop app is open.

Then ask: reply `go` to schedule, or say what to change. Only an explicit go from the user counts as approval.

## 6. Schedule (only after "go")

First recheck the clock: if any slot in the table has already passed (the user took a while to say go), move it and every later nudge forward by the same rules, show the updated table, and ask for `go` again.

Then create one task per nudge with the scheduled-tasks tool (`create_scheduled_task`):

- **Series id**: a short kebab-case form of the subject plus the last four digits of the parent ts, e.g. `q3-budget-3259`, so two series never share task ids. If `list_scheduled_tasks` already shows tasks starting with that id, append `-2`, `-3`, ….
- `taskId`: `<series id>-nag-<n>` (e.g. `q3-budget-3259-nag-1`).
- `title`: `<Subject> nag <n>/<total> (<date in their time>)`.
- `fireAt`: ISO 8601 with *their* UTC offset on that date, e.g. `2026-11-02T11:00:00-06:00`.
- `prompt`: the template below, fully filled in. Each run starts with no memory, so leave nothing out.

```
You are <USER FIRST NAME>'s nagging bot. Post ONE nudge in a Slack thread, unless it's no longer needed.

Context: <two or three sentences: what's being chased, why it matters, who owes the answer (name, Slack id, timezone), and the anchor message, with its date>.

Thread: channel <CHANNEL_ID>, parent message ts <TS> (<URL>). Nudges are posted from <USER FIRST NAME>'s account (Slack id <USER_ID>) and start with 🤖, which Slack may return as :robot_face:.

Steps:
1. Read the thread with the Slack connector (slack_read_thread, channel_id <CHANNEL_ID>, message_ts <TS>).
2. Decide whether it has been answered. Look only at messages with a ts later than <ANCHOR_TS> (the anchor: "<ANCHOR MESSAGE QUOTE>"). Ignore nudges: messages from <USER_ID> that start with 🤖 or :robot_face:. It has been answered if anyone other than <USER_ID> has posted something that relays the answer or a status: done, declined, a question back, can't be reached, stop nagging, and so on; or if <USER_ID> has posted that it's settled ("got it", "never mind", "stop"). "Still waiting", "no reply yet" and <USER_ID>'s own follow-up pings do NOT count.
   If it has been answered, post nothing, then clean up: list the scheduled tasks whose ids start with <SERIES_ID>-nag- (list_scheduled_tasks), delete the ones still pending with delete_scheduled_task (the user approved this when scheduling the series; touch no other tasks), and report a one-line summary of the answer and which tasks you deleted. Stop there.
3. If a nudge (as defined above) was posted in the thread within the last 20 hours, post nothing: an earlier task in the series already covered this slot. Report that and stop.
4. Check the time in <IANA TZ>. If it's a weekday between 09:00 and 17:00 there, post the message below as a thread reply with slack_send_message (channel_id <CHANNEL_ID>, thread_ts <TS>). Otherwise don't post now: create a new scheduled task (create_scheduled_task) with taskId <THIS TASK ID>-late, the same title, and this same prompt word for word, firing at the next 11:00 <IANA TZ> that's on a weekday (today if it's a weekday and before 11:00 there), with that date's real UTC offset. Report that you rescheduled it.
5. Post the message exactly as given. Don't add anything else, and don't send anything to anyone else.

Message:
<MESSAGE>
```

Create all of them, then report in a short table: task id, their time, your time. Mention the permission mode the tasks were saved in (the tool result says it), and that the user can edit, pause or delete them from **Scheduled** in the sidebar.

## Rules

- Post only in the given thread, and tag only the person being nagged.
- Never schedule before the user confirms, and never change the schedule or messages after "go" without asking again.
- Clean up when done: once a task finds the thread answered, it deletes the rest of its own series, and nothing else.
- Never hand a nudge to Slack's own message scheduling: a Slack-scheduled message can't recheck the thread or be cancelled by the cleanup.
