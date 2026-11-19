# Relay demonstration video

**Target length · 6 minutes.** The script uses three speakers. Replace the bracketed names and contributions before recording. Read the quoted lines aloud and use the screen directions as cues.

## Before recording

- Run the automated tests and rehearse the browser walkthrough in the README.
- Verify that **Settings → Check connection** reports an enabled device. Keep the registered Android phone online with an SMS-capable SIM. Arrange for the consenting recipient to confirm receipt if possible.
- Use a demo database with an empty history or your group's authorized attempts. Keep `.env`, the textbee dashboard, and notifications out of the recording. Mask the recipient's number wherever it appears, including the form, preview, history, and any phone footage. Blur the full batch ID.
- If delivery callbacks are unavailable, rehearse **Refresh status**. Record the status that actually appears.

## Recording script

### 0:00–0:40 · Introduction · Speaker 1

**On screen** — Open Relay's dashboard in the browser.

> “Hi, we're [group name] from IT 120. This is Relay, our SMS messaging web application. It lets us write a text in the browser, check the recipient and message before sending, and look up the result later. We use textbee.dev to send the message through a registered Android phone. We'll demonstrate a validation error first, then send a real SMS to someone who agreed to receive our test.”

### 0:40–1:20 · Dashboard · Speaker 1

**On screen** — Point to the four summary cards, the seven-day chart, and **Recent messages**.

> “The dashboard summarizes what we've done in Relay. These numbers come from the sending attempts stored in SQLite. The total counts every recorded attempt. Submitted means the provider accepted the request and delivery confirmation is still pending. Delivered counts the attempts with a delivery report. The chart groups attempts by day, and the recent messages section gives us a shortcut back to the latest ones.”

If history is empty, add “This workspace starts with no messages. We'll come back after sending one.”

### 1:20–2:20 · Compose, preview, and validate · Speaker 2

**On screen** — Open **Send SMS**. Enter `09171234567` as the invalid input and type the following demo message.

> IT 120 demo from Relay. This is our SMS delivery test.

**Speaker 2**

> “As I type, the phone preview shows the recipient and the text. The composer also shows a character count and an estimate of how many SMS segments the message uses. Before trying the real send, I'll submit this number in local format so we can see how the app handles invalid input.”

**On screen** — Click **Send SMS** and pause on the validation error. Replace the invalid input with the consenting recipient's real number in international format. Keep it masked in the recording.

> “Django checks the number on the server and asks for a valid international number. This submission didn't create a sending attempt, and the draft is still here. I'll correct the number and check the preview once more.”

### 2:20–3:30 · Live SMS and provider response · Speaker 2

**On screen** — Click **Send SMS** once. On **Message Details**, show the result banner and current status. If a batch ID appears, mask its value.

> “Relay saves the sending attempt, then asks textbee to send the SMS through our Android phone's SIM. This page shows the message we submitted and the status Relay has recorded. When textbee returns a batch ID, Relay uses it to look up the attempt again.”

Use the line that matches what appears on screen.

- **Submitted** — “textbee accepted the request. Delivery confirmation is still pending. I'll use Refresh status to check for an update.”
- **Delivered** — “Relay now shows Delivered because textbee received a delivery report from the carrier.”
- **Failed** — “The attempt failed. Relay saved it in history and shows the error we can use to investigate.”
- **Unknown** — “Relay couldn't confirm the outcome. We'll check the textbee dashboard privately before deciding whether to send again.”

**On screen** — If a batch ID is available, click **Refresh status**. If the status stays Submitted, leave it visible and move on. With the recipient's permission, you can briefly show the test message on their phone. If the initial send fails during recording, resolve the issue off camera and record the live-send segment again when ready.

### 3:30–4:15 · Message history · Speaker 3

**On screen** — Open **Message History**. Search for `IT 120 demo`, choose the status you actually observed, then open **Details** on the matching row.

> “Here is the attempt we just made. I'll search using part of the message, then narrow the result by its current status. The history records the time and status and shows a preview of the text. I can open the full record from here. If we return to the dashboard, its counts reflect the attempt we just made.”

### 4:15–5:05 · Contacts and Settings · Speaker 3

**On screen** — Open **Contacts** and use a prepared demo contact for the consenting recipient. Choose the contact's **Send SMS** action and show that it fills the number. Return to **Settings** without submitting another message.

> “Contacts let us save a recipient's name and number. We can search, edit, or remove a contact. I'll open the composer from this contact's row. Relay fills in the number for us, and we can still check the preview before sending. Settings shows whether the API key and the Android device ID are configured. Check connection asks textbee whether it recognizes the configured device and whether the device is enabled.”

### 5:05–6:00 · Technologies, contributions, and closing · All speakers

**On screen** — Return to the dashboard. Each speaker names one contribution they actually made.

> **Speaker 1** — “Django handles the forms, pages, and database operations. SQLite stores our contacts and message attempts. I'm [name], and I worked on [specific contribution].”
>
> **Speaker 2** — “JavaScript updates the preview as we type. The interface adapts to desktop and phone screens. I'm [name], and I worked on [specific contribution].”
>
> **Speaker 3** — “Django uses the textbee API to submit messages and check their status. Our automated tests simulate provider responses and use no live SMS. I'm [name], and I worked on [specific contribution].”

> **Closing** — “That was our Relay demonstration for IT 120. Thank you for watching.”

## Submission checklist

- [ ] Install from the pinned dependencies, apply migrations, and start Django from a clean clone.
- [ ] Run the automated tests and check desktop and phone layouts.
- [ ] Send a live SMS to a consented recipient and record only the observed provider result.
- [ ] Confirm that credentials, the local database, and private screenshots are excluded from Git and the video.
- [ ] Push the source and documentation to the actual group repository.
- [ ] Replace the group-member placeholders in the README with accurate contributions.
- [ ] Record and review the 3–10 minute video.
- [ ] Verify the instructor can open the submitted repository and video links.
