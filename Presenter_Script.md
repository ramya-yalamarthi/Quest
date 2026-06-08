# Presenter Script — ServiceNow → PostgreSQL Automated Ticket Sync

_Read each slide's script below while it's on screen. Notes are also embedded directly in the PPTX (View → Notes / Presenter View in PowerPoint)._

## Slide 1: ServiceNow → PostgreSQLAutomated Ticket Sync

Good [morning/afternoon]. Today I'm going to walk you through a project I just completed: fully automating the flow of tickets from our ServiceNow instance into a PostgreSQL database. I'll cover the problem we were solving, how I built it, how I made it run automatically and reliably, and then show the trade-offs so we can decide together whether this is production-ready or needs further investment.

## Slide 2: Agenda

Quick run-through of the agenda — I'll move through the architecture and implementation, then spend extra time on the trade-offs slide because that's where I'd like your input on next steps.

## Slide 3: The Problem & The Goal

Let's start with why we needed this. Our tickets live inside ServiceNow, which is great for managing support workflows, but it's isolated from our own systems and databases — so any time we wanted to analyze or cross-reference ticket data with our application data, it meant manual CSV exports. The ask had two parts: first, do a one-time migration of everything that already exists; second — and this is the more valuable part — make it so any new ticket automatically lands in our database within seconds, forever, with no manual work.

## Slide 4: Solution at a Glance — The Full Data Flow

Here's the entire pipeline in one picture, top to bottom. When someone creates or edits a ticket in ServiceNow, a small rule I configured fires automatically and sends a notification out to the public internet. That notification travels through a secure tunnel to a small program running on my machine, which then asks ServiceNow for the full, authoritative copy of that ticket, and writes it into Postgres. End to end, this happens in about 2 to 5 seconds — fully automatically, no human in the loop.

## Slide 5: Step 1 — Setting Up the Database

First step was the database itself. I deliberately created a brand new database called 'servicenow_tickets' rather than touching our existing project database — that way there's zero risk of breaking anything we already depend on. I designed the table to mirror ServiceNow's important fields, and — this is a small but important detail — I also store the complete original record as JSON, as a safety net, so we never permanently lose any data even if we didn't think to map a particular field into its own column. The most important design decision was making ServiceNow's internal ID, sys_id, a UNIQUE key in our table — that's what lets us safely 'upsert': insert a ticket if it's new, update it if we've already seen it. That single decision is what makes the whole system safe to re-run as many times as we want without ever creating duplicate rows.

## Slide 6: Step 2 — Importing All Existing Tickets (Backfill)

With the table ready, I wrote a backfill script — basically a one-time bulk importer. It calls ServiceNow's REST API, which is the standard way external systems read ServiceNow data, pages through all the records, and writes each one into Postgres. I ran it, and it successfully pulled in all six hundred ninety-nine existing tickets — I verified this directly with a SQL count query against the database, not just trusting the script's own output. And critically — this script isn't a 'run once and forget' tool. Because of the upsert design from the previous slide, we can run it again anytime — for example as a safety-net catch-up mechanism — and it will never create duplicate data.

## Slide 7: Step 3 — Real-Time Sync, Part 1: The Webhook Receiver

Now for the live-sync piece, which has three parts working together — let's take them one at a time. First: the webhook receiver. This is a small, purpose-built web service I wrote that does one job — listen for 'a ticket just changed' notifications. When it receives one, it does three things: checks a secret key so random internet traffic can't feed it fake data, then — and this is a deliberate security and correctness choice — it does NOT trust the data inside the notification. Instead it goes back to ServiceNow and asks for the full, current, authoritative version of that specific ticket, and only then writes it to Postgres. This guards against any tampering or partial/stale data in transit.

## Slide 8: Step 3 — Real-Time Sync, Part 2: Exposing It Securely (Tunnel)

Second piece — the tunnel. Here's the challenge: ServiceNow lives in the cloud and needs to 'call' our webhook receiver, but our receiver runs on a local machine, which by design cannot be reached directly from the internet — that's actually a sensible security default we don't want to compromise. The solution is a tool called Cloudflare Tunnel. It creates a secure, temporary public web address, and anything sent to that address gets forwarded straight through, encrypted, to our local machine — without us opening any firewall ports or exposing the machine directly. It's the same category of technology many companies use for secure remote access.

## Slide 9: Step 3 — Real-Time Sync, Part 3: The ServiceNow Business Rule

Third and final piece of the live-sync puzzle — a 'Business Rule' inside ServiceNow. This is essentially a small piece of automation logic that lives inside ServiceNow itself. I configured it — directly through ServiceNow's own API, so no manual click-through was needed — to fire automatically every time a ticket is created or updated, and to send a small notification out to our tunnel's address. The key point here: nobody using ServiceNow has to change how they work AT ALL. They create a ticket exactly like they always have. This rule fires silently in the background and kicks off the entire chain we just walked through.

## Slide 10: Putting It All Together — What Happens When You Create a Ticket

Let's bring it all together — this is the complete chain, restated as a single story. You create a ticket, exactly as you always have. ServiceNow saves it and, completely invisibly to you, fires our rule. That rule pings our tunnel, the tunnel forwards it to our receiver, the receiver double-checks with ServiceNow for the authoritative data, and writes it to Postgres. I want to stress: this is not theoretical — I tested this exact chain live, end to end, multiple times, and I'll show you the proof in a few slides.

## Slide 11: Step 4 — Making It Durable: Background Services

Now — making it durable. If I'd just run these two programs from a terminal window, closing that window would have killed the whole sync. So instead, I registered both pieces — the webhook receiver and the tunnel — as proper background services using macOS's own service manager, called launchd. This is literally the same system macOS uses to run its own internal services. I configured them to start automatically the moment you log in, and to automatically restart themselves if they ever crash for any reason. The net effect: this sync now 'just runs', indefinitely, in the background — nobody has to remember to start it, and it recovers from problems on its own.

## Slide 12: The Tricky Bit — Solved: Self-Healing Tunnel Addresses

Here's a subtlety I ran into — and solved — that's worth highlighting because it shows the difference between a 'demo that works once' and something genuinely reliable. The free version of the tunnel tool generates a brand new, random public web address every single time it restarts. If that address changes but ServiceNow's rule is still pointing at the old, dead address, the entire sync silently breaks with no warning. So I built a small watcher program that continuously monitors for that address changing, and the instant it does, automatically calls ServiceNow's API and rewrites the Business Rule to point at the new address — with no human involvement. I actually watched this happen live during setup: the address changed, the watcher caught it, fixed ServiceNow automatically, and a test ticket flowed through the brand new address successfully within seconds. That's the kind of self-healing behavior you want in something that has to run unattended.

## Slide 13: Live Proof — This Was Tested End-to-End, Not Just Assumed

I want to be very clear that none of this is theoretical or 'should work' — I tested every single stage independently, and then tested the whole chain end to end with real tickets. I created actual test tickets directly inside ServiceNow, and watched them appear automatically in Postgres within about five seconds, with zero manual intervention. I verified the database connection, the data import count, the webhook responding and logging each upsert, the tunnel being publicly reachable, the Business Rule existing and firing, the self-healing recovery — and the background services reporting healthy status. Every checkbox on this slide was independently confirmed, not assumed.

## Slide 14: Advantages vs. Considerations

Now let's talk trade-offs honestly — this is the part where I'd really like your input. On the left: what this approach gets us, and it's quite a lot — fully automatic syncing, safe to re-run without creating duplicates, self-healing, survives reboots, and built with security in mind from the start using a secret key and re-verification against the source of truth. On the right: the honest limitations. The biggest one is that this currently depends on my laptop being on and connected — if it's off, new tickets simply won't sync until it's back (though nothing is lost forever; we can always re-run the backfill to catch up). The free tunnel also isn't an enterprise-grade guaranteed-uptime product, and there's no retry queue if a single notification gets dropped. For a short-term win and for proving the concept, this is excellent and fully working today. For a long-term, mission-critical setup, I'd recommend we discuss moving the receiver to a proper server with a fixed address — which is a relatively small follow-up step from here.

## Slide 15: Day-to-Day: It Runs Itself

One more thing worth mentioning — operability. This isn't something that requires me to remember to start it every morning. It starts itself on login and keeps itself alive. If anyone ever wants to double check it's healthy, there are two one-line commands that take about ten seconds combined. And if we ever suspect something was missed, there's a single safe command that re-syncs everything from scratch without creating any duplicates. I've also written up full documentation in the repo so any teammate could pick this up without me.

## Slide 16: Recommendations & Possible Next Steps

So, where does this leave us? As of today, this is fully working, fully automated, and I've tested it end to end — it's ready to use right now. If we decide we want to invest further, the natural next steps would be: moving the receiver to a proper server so it doesn't depend on my laptop, adding a retry mechanism so we never lose even a single notification, adding monitoring so we'd be alerted if it ever stopped, and potentially opening this data up to the wider team with proper access controls. My personal recommendation is to run it as-is for a while, prove out the value it delivers, and then make a more informed call on whether the additional investment in hosting is worth it.

## Slide 17: Questions?

That's the full picture — from the original problem, through the design decisions, the build, the testing, and an honest look at the trade-offs. I'm happy to open it up for questions, walk through any part of it live, show you the actual data in the database, or go deeper into any of the trade-offs we should plan around.
