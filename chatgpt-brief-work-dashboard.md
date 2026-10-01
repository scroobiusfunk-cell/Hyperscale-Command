# Brief: build a "Daily Work Dashboard" web page

Paste this whole file into ChatGPT (or attach it). Ask for **one self-contained `index.html`** (inline CSS and JS, no build step), then open it in a browser.

## What it is

A one-page morning dashboard for a senior commissioning manager at a general contractor, working on a data center campus program. It turns today's calendar, email and Teams chat into a ranked picture of the day: what needs them, who is waiting on them, and what they promised.

It has two modes:

1. **Snapshot mode (required, must work offline).** The page ships with a hard-coded sample dataset (below) and renders fully from it.
2. **Live refresh (stretch goal).** A "Refresh" button that pulls calendar, inbox, sent mail and chat from Microsoft 365, sends a digest to an LLM, and re-renders from the JSON it returns. If you cannot reach Microsoft 365 from a static page, build the button as a stub with the exact prompt and data shapes below, and say plainly what is stubbed. Do not fake success.

## Layout

Single column on phones, two columns at 900px and up (340px left rail, flexible right column). Max width 1080px, 16px side gutters, no horizontal scroll.

**Hero**
- Date line, e.g. "Tuesday, 30 September · CDR East Campus".
- Headline (the day in one line, under 14 words), large condensed type.
- Three "gauge" chips: calendar item count plus number of double-booked windows, number of people waiting, and "Clear from 4:00 PM" (first free time after the last live meeting).
- Status line ("Snapshot at 10:32 AM CT"), plus the Refresh, Deeper check and Stop buttons (hidden unless live refresh is available).

**Left rail (sticky on desktop): "Today" timeline**
- Vertical time axis from 6:30 AM to about 4:30 PM, 1.15px per minute, hour labels on hairlines.
- Events are absolutely positioned blocks. Overlapping events are laid out side by side in lanes (greedy lane assignment within each overlapping cluster), so side by side means double-booked.
- Event styles: normal (blue left border), **key** (orange left border, tinted background, "needs you"), **own block** (grey left border, diagonal hatch), **cancelled** (dashed border, 55% opacity, struck-through title).
- A "Now" line in orange with a label, positioned by Central time and hidden if the data date is not today or the time is outside the axis. Updates every minute.
- A dashed green "Clear from X" block after the last non-cancelled event.
- Legend: Needs you, Site / QTS, Your own block.

**Right column, four sections**
1. **Top 3.** Cards styled like luggage tags: a coloured rank bar on the left, a ring "hole" punched near the top-left, rounded right corners. Rank 1 orange, rank 2 amber, rank 3 blue. Each card has title, summary, a bullet list of evidence, a "Next" box with the suggested move, and "Open in Outlook / Open in Teams" links.
2. **Slipping through the cracks.** A checklist of threads where someone is waiting or a clock is running. Each row: checkbox, bold title, coloured pill (hot / warn / ok), body, and a muted "Next:" line.
3. **People to follow up with.** Checklist. Each row: name, muted age ("yesterday 3:44 PM"), body.
4. **Commitments you've made.** Checklist, with some pre-ticked (done) items shown faded.

Below that: a caveats note (left amber border) saying what the data did and did not cover, and a small "Clear ticks" button.

## Behaviour details

- Checkbox ticks persist per day in `localStorage` under a key like `dash-ticks-YYYY-MM-DD`, keyed by a hash of title plus body. Wrap every storage call in try/catch and make the page work without it.
- Build all DOM with `createElement` and `textContent`, never `innerHTML` with data. Only allow link URLs whose host is `outlook.office365.com`, `outlook.office.com` or `teams.microsoft.com`.
- Respect `prefers-reduced-motion`. Visible focus rings. Checkbox `aria-label="Mark done"`.
- Keyboard and screen-reader usable. No colour-only meaning (pills carry text).
- Render the timeline in Central time (`America/Chicago`) using `Intl.DateTimeFormat`.

## Visual design

Industrial / jobsite feel: warm paper-grey background, navy ink, safety-orange accent, hairline rules, square-ish corners (3px), no gradients or shadows apart from the hatch pattern.

- Fonts (Google Fonts): **Barlow Condensed** (500/600/700) for headings, **Source Sans 3** (400/600/700) for body. Fall back to system sans.
- Light palette: bg `#E9EDF0`, panel `#FFFFFF`, ink `#14263B`, muted `#56687A`, rule `#C9D2DA`, hot `#D9580B`, caution `#E0B000`, live `#2E7D4F`, self `#8A9BAB`, site `#3A6EA5`, with soft tints `#FBE7DA`, `#FBF3D2`, `#DDEFE4`.
- Dark palette (via `prefers-color-scheme: dark`, plus a `data-theme` override): bg `#0F1A26`, panel `#172536`, ink `#E6EDF3`, muted `#9FB0C0`, rule `#2A3C50`, hot `#F07A33`, caution `#F2C94C`, live `#4CB77D`, self `#6F8193`, site `#6C9FD6`, tints `#3A2517`, `#3A3217`, `#183324`.
- Define all colours as CSS variables on `:root`. Give `body` an explicit background.
- Hero has a 4px ink bottom border. Headline uses `clamp(34px, 7vw, 56px)`.

## Data shape (the whole page renders from one object)

```js
{
  date: "2026-09-30", asOf: "10:32 AM CT", source: "snapshot",
  headline: "...",
  links: { m1: "https://outlook.office365.com/...", t1: "https://teams.microsoft.com/..." },
  events: [ { id:"e1", s:"06:30", e:"07:00", t:"Title", n:"short note", self:false } ],
  keyEvents: ["e8"], cancelledEvents: ["e9"],
  top3:  [ { title, summary, evidence:[...], next, refs:["m1","t1"] } ],
  slipping:    [ { title, tag, tone:"hot|warn|ok", body, next, refs } ],
  people:      [ { name, when, body, refs } ],
  commitments: [ { title, tag, tone, body, done:false } ],
  caveats: "..."
}
```

`refs` are keys into `links`. Show at most 3 links per item.

## Sample data (use this for the snapshot; it is illustrative, names are placeholders)

Headline: "Fix one fact, answer Josh, and get the OFCI report out by 1:00."

Events (id, start, end, title, note, own block?):
e1 06:30-07:00 Start day practice (own) · e2 06:30-07:00 DC4 Daily Huddle · e3 07:00-08:30 Cx Coordination DC4/DC5 · e4 07:00-08:00 DC2 Cx/Construction · e5 08:00-09:00 DC4 CEI walk · e6 08:30-09:00 CDR1 Team Meeting · e7 09:00-10:00 Admin prep (own) · e8 10:00-12:00 DC5 energization "1100 loading dock" · e9 10:00-10:45 QTS Quality weekly "likely cancelled" · e10 10:00-11:00 CEI trade partner · e11 11:00-12:00 AI dashboard (own) · e12 11:45-12:00 All Hands "mandatory" · e13 12:00-13:00 Lunch (own) · e14 12:00-12:30 Hammertech (own) · e15 12:30-13:00 OFCI report "for Ethan" (own) · e16 13:00-13:30 OFCI Coordination · e17 13:30-14:30 Mo weekly sync · e18 14:30-15:00 Issue catch up (own) · e19 15:00-16:00 DC4 CxAlloy review "vendors asked" · e20 15:00-15:30 Meeting prep (own) · e21 15:30-16:00 Power Coordination.
Key: e8, e12, e15, e19. Cancelled: e9.

Top 3:
1. **Correct the Cerio-Delta attendance point.** The 9:18 vendor email says Cerio-Delta was not on this morning's call; Mason replied to everyone that he attends daily, and an executive escalation is now built on that email. Evidence: Mason posted his address in a site meeting chat at 7:20 AM (reads like a roll call, can't confirm it was the same call); his reply went to five people with five more copied; the PDU items themselves are still open, only the attendance line is in question. Next: check which call was meant; if he was on it, send a two-line reply-all thanking him, correcting the line and asking for dates on the three PDU items.
2. **Answer Josh on today's Cx leadership meeting.** He asked at 7:57 and 8:00 for a go-ahead to pull the DC4 and DC5 Cx teams, QA/QC and support staff together today; no reply in Teams since yesterday. Evidence: he was frustrated after being called out in the morning meeting; his expectations email on PEIs, clean walks and energizations went out at 9:50. Next: give him the go-ahead and a slot; 4:00 PM is the only time both are clear of site meetings.
3. **OFCI report to Ethan before 1:00.** The 12:30 block sits behind Hammertech, the All Hands and the energization. Evidence: no email to or from Ethan about the report in the last week, so the expected format is unknown. Next: move Hammertech to 4:00 and use 12:00 to 1:00 for the report.

Slipping:
- DC6 IMVG/MVG checklists (tag "QTS wants them this week", hot): chased since 9/8; the client's rep added this morning that the client and its design firm need them this week. Josh owns it. Next: ask Josh for a date to give the client today.
- Matt's DC4 executive escalation (tag "Unread", warn): sent at 10:23, cites a one-week minimum exposure. Next: read it before the 3:00 CxAlloy review.
- New client PM, Rob Thornton (tag "Unread", warn): asked to review the Cx process and coordinate with the team. Next: short welcome and an invite to tomorrow's 7:00 Cx call.

People: Andrew Whall, VTC (10:16 AM) asked whether there is a call other than 3:00 · Mo (yesterday 3:44 PM) asked for comments on the functionality list, sync is 1:30 today · Steven McCandless (yesterday 8:21 AM) you asked him for a conversation, can't see whether it happened · Matthew Underwood (yesterday 12:02 PM) out Oct 22 to 27 and asked for cover, no reply.

Commitments: Vendor return dates for DC4 ("2 of 5 replied", warn) · OFCI report for Ethan ("Due 1:00 PM", hot) · DC4 1100 Cx micro schedule for Zac Riley ("Sent 9/29", ok, done).

Caveats: "Snapshot from calendar, inbox and sent mail since 9/24, and Teams since 9/28. OneDrive wasn't searched. CxAlloy and Procore notifications left out on purpose."

## Live refresh spec (stretch)

If you can wire it up:

1. In parallel, fetch: today's calendar; inbox since 3 days ago; sent mail since 3 days ago; Teams messages to the user since yesterday; Teams messages from the user since yesterday. Show one status chip per source (running / ok with count / failed). If every source fails, keep the old data and show why. If some fail, continue and list them in the caveats.
2. Drop notification noise (no-reply senders, Procore, CxAlloy).
3. Give every item a short id (`e1…` events, `m` inbox, `s` sent, `t` Teams-to-user, `u` Teams-from-user) and keep a map of id to web link.
4. Send the LLM this instruction plus the JSON digest, and require a JSON-only reply:
   - Act as the user's executive assistant; use only facts in the data; never invent people or dates; say plainly when something can't be confirmed.
   - Every top-3 item needs evidence lines. "Next" moves are one or two practical, non-confrontational sentences, and any "don't do X" is paired with a constructive alternative.
   - A thread is "waiting on the user" if someone asked or @mentioned them and nothing in sent mail or their Teams messages answers it. Commitments come from sent mail and the user's own calendar blocks.
   - Ignore meeting invite emails unless they change today; if a message says a meeting today is cancelled, put its id in `cancelledEvents`.
   - Plain English, no em dashes, no all caps. Times in email and Teams data are UTC, calendar times are Central wall clock; write everything in Central.
   - Limits: top3 exactly 3, slipping up to 4, people up to 6, commitments up to 5, refs max 2 per item.
   - Reply schema: `headline, top3[], slipping[], people[], commitments[], keyEvents[], cancelledEvents[], eventNotes{id:label}, caveats`.
5. Validate the reply (top3 must be an array), merge it into the data object above with `source:"live"`, cache it in `localStorage`, re-render. Handle: user stopped (AbortController), rate limited, bad JSON, session expired, with a plain-English message each and the previous version left on screen.
6. Offer a quick check and a slower "Deeper check" using a stronger model, with a note about usage.

## Deliverable and honesty rules

- One `index.html`, works by double-clicking it, snapshot mode fully functional.
- Works in light and dark mode and at phone width.
- At the end, list what you built, what you stubbed, and anything you could not verify. Do not claim live Microsoft 365 or LLM calls work unless you actually implemented and tested them.
